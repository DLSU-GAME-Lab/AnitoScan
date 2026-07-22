#include "IPCClientPlatform.h"

#if !defined(_WIN32)

#include <array>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <csignal>
#include <cstring>
#include <fcntl.h>
#include <mutex>
#include <poll.h>
#include <spawn.h>
#include <string>
#include <thread>
#include <unistd.h>
#include <utility>
#include <vector>
#include <sys/wait.h>

extern char** environ;

namespace {

constexpr std::size_t kReadBufferSize = 4096;
constexpr std::size_t kMaximumLineSize = 16 * 1024 * 1024;
constexpr auto kGracefulShutdownTimeout = std::chrono::milliseconds(750);

void CloseDescriptor(int& descriptor) {
	if (descriptor >= 0) {
		close(descriptor);
		descriptor = -1;
	}
}

bool SetCloseOnExec(int descriptor, std::string& error) {
	const int flags = fcntl(descriptor, F_GETFD);
	if (flags < 0 || fcntl(descriptor, F_SETFD, flags | FD_CLOEXEC) < 0) {
		error = std::strerror(errno);
		return false;
	}
	return true;
}

bool NormalizeDescriptor(int& descriptor, std::string& error) {
	if (descriptor > STDERR_FILENO) {
		return SetCloseOnExec(descriptor, error);
	}

	const int replacement = fcntl(descriptor, F_DUPFD_CLOEXEC, STDERR_FILENO + 1);
	if (replacement < 0) {
		error = std::strerror(errno);
		return false;
	}
	close(descriptor);
	descriptor = replacement;
	return true;
}

bool CreatePipe(std::array<int, 2>& descriptors, std::string& error) {
	if (pipe(descriptors.data()) != 0) {
		error = std::strerror(errno);
		return false;
	}

	if (!NormalizeDescriptor(descriptors[0], error) ||
		!NormalizeDescriptor(descriptors[1], error)) {
		CloseDescriptor(descriptors[0]);
		CloseDescriptor(descriptors[1]);
		return false;
	}
	return true;
}

std::string SpawnError(int code) {
	return std::strerror(code);
}

bool ProcessGroupExists(pid_t group) {
	if (group <= 0) return false;
	if (kill(-group, 0) == 0) return true;
	return errno == EPERM;
}

class PosixIPCClientPlatform final : public IPCClientPlatform {
public:
	~PosixIPCClientPlatform() override {
		Shutdown();
	}

	bool Start(
		const std::string& executable,
		const std::vector<std::string>& arguments,
		LineHandler stdoutHandler,
		LineHandler stderrHandler,
		std::string& error) override {
		if (running.load()) {
			error = "a backend process is already running";
			return false;
		}

		Shutdown();

		std::array<int, 2> stdinPipe{ -1, -1 };
		std::array<int, 2> stdoutPipe{ -1, -1 };
		std::array<int, 2> stderrPipe{ -1, -1 };

		if (!CreatePipe(stdinPipe, error) ||
			!CreatePipe(stdoutPipe, error) ||
			!CreatePipe(stderrPipe, error)) {
			CloseDescriptor(stdinPipe[0]);
			CloseDescriptor(stdinPipe[1]);
			CloseDescriptor(stdoutPipe[0]);
			CloseDescriptor(stdoutPipe[1]);
			CloseDescriptor(stderrPipe[0]);
			CloseDescriptor(stderrPipe[1]);
			return false;
		}

		const int writeFlags = fcntl(stdinPipe[1], F_GETFL);
		if (writeFlags < 0 || fcntl(stdinPipe[1], F_SETFL, writeFlags | O_NONBLOCK) < 0) {
			error = std::strerror(errno);
			CloseAll(stdinPipe, stdoutPipe, stderrPipe);
			return false;
		}

#if defined(__APPLE__)
		if (fcntl(stdinPipe[1], F_SETNOSIGPIPE, 1) < 0) {
			error = std::strerror(errno);
			CloseAll(stdinPipe, stdoutPipe, stderrPipe);
			return false;
		}
#else
		std::signal(SIGPIPE, SIG_IGN);
#endif

		posix_spawn_file_actions_t actions;
		posix_spawnattr_t attributes;
		bool actionsInitialized = false;
		bool attributesInitialized = false;

		auto failSetup = [&](int code) {
			error = SpawnError(code);
			if (actionsInitialized) posix_spawn_file_actions_destroy(&actions);
			if (attributesInitialized) posix_spawnattr_destroy(&attributes);
			CloseAll(stdinPipe, stdoutPipe, stderrPipe);
			return false;
		};

		int result = posix_spawn_file_actions_init(&actions);
		if (result != 0) return failSetup(result);
		actionsInitialized = true;

		result = posix_spawnattr_init(&attributes);
		if (result != 0) return failSetup(result);
		attributesInitialized = true;

		auto addAction = [&](int code) {
			if (result == 0 && code != 0) result = code;
		};

		addAction(posix_spawn_file_actions_adddup2(&actions, stdinPipe[0], STDIN_FILENO));
		addAction(posix_spawn_file_actions_adddup2(&actions, stdoutPipe[1], STDOUT_FILENO));
		addAction(posix_spawn_file_actions_adddup2(&actions, stderrPipe[1], STDERR_FILENO));
		for (int descriptor : { stdinPipe[0], stdinPipe[1], stdoutPipe[0], stdoutPipe[1], stderrPipe[0], stderrPipe[1] }) {
			addAction(posix_spawn_file_actions_addclose(&actions, descriptor));
		}
		if (result != 0) return failSetup(result);

		sigset_t emptyMask;
		sigemptyset(&emptyMask);
		result = posix_spawnattr_setsigmask(&attributes, &emptyMask);
		if (result != 0) return failSetup(result);

		sigset_t defaultSignals;
		sigemptyset(&defaultSignals);
		sigaddset(&defaultSignals, SIGPIPE);
		sigaddset(&defaultSignals, SIGTERM);
		sigaddset(&defaultSignals, SIGINT);
		sigaddset(&defaultSignals, SIGHUP);
		result = posix_spawnattr_setsigdefault(&attributes, &defaultSignals);
		if (result != 0) return failSetup(result);

		short flags = POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_SETSIGMASK | POSIX_SPAWN_SETSIGDEF;
#if defined(__APPLE__) && defined(POSIX_SPAWN_CLOEXEC_DEFAULT)
		flags |= POSIX_SPAWN_CLOEXEC_DEFAULT;
#endif
		result = posix_spawnattr_setflags(&attributes, flags);
		if (result != 0) return failSetup(result);
		result = posix_spawnattr_setpgroup(&attributes, 0);
		if (result != 0) return failSetup(result);

		std::vector<std::string> argumentStorage;
		argumentStorage.reserve(arguments.size() + 1);
		argumentStorage.push_back(executable);
		argumentStorage.insert(argumentStorage.end(), arguments.begin(), arguments.end());

		std::vector<char*> argumentPointers;
		argumentPointers.reserve(argumentStorage.size() + 1);
		for (std::string& argument : argumentStorage) {
			argumentPointers.push_back(argument.data());
		}
		argumentPointers.push_back(nullptr);

		pid_t childPid = -1;
		result = posix_spawnp(
			&childPid,
			executable.c_str(),
			&actions,
			&attributes,
			argumentPointers.data(),
			environ);

		posix_spawn_file_actions_destroy(&actions);
		posix_spawnattr_destroy(&attributes);

		CloseDescriptor(stdinPipe[0]);
		CloseDescriptor(stdoutPipe[1]);
		CloseDescriptor(stderrPipe[1]);

		if (result != 0) {
			error = SpawnError(result);
			CloseDescriptor(stdinPipe[1]);
			CloseDescriptor(stdoutPipe[0]);
			CloseDescriptor(stderrPipe[0]);
			return false;
		}

		{
			std::lock_guard<std::mutex> lock(stateMutex);
			pid = childPid;
			processGroup = childPid;
			stdinWrite = stdinPipe[1];
			stdoutRead = stdoutPipe[0];
			stderrRead = stderrPipe[0];
			stdoutLineHandler = std::move(stdoutHandler);
			stderrLineHandler = std::move(stderrHandler);
			stopping.store(false);
			stopReaders.store(false);
			stdoutDone.store(false);
			stderrDone.store(false);
			running.store(true);
		}

		try {
			// The wait thread owns child reaping. Start it first so later worker
			// construction failures still have a process owner.
			waitThread = std::thread(&PosixIPCClientPlatform::WaitLoop, this, childPid);
			stdoutThread = std::thread(
				&PosixIPCClientPlatform::ReaderThread,
				this,
				stdoutRead,
				stdoutLineHandler,
				&stdoutDone);
			stderrThread = std::thread(
				&PosixIPCClientPlatform::ReaderThread,
				this,
				stderrRead,
				stderrLineHandler,
				&stderrDone);
		}
		catch (const std::exception& exception) {
			error = exception.what();
			Shutdown();
			return false;
		}

		return true;
	}

	bool Send(std::string_view data, std::string& error) override {
		std::lock_guard<std::mutex> lock(writeMutex);
		if (!running.load() || stopping.load() || stdinWrite < 0) {
			error = "backend stdin is not available";
			return false;
		}

		std::size_t offset = 0;
		while (offset < data.size()) {
			const ssize_t written = write(stdinWrite, data.data() + offset, data.size() - offset);
			if (written > 0) {
				offset += static_cast<std::size_t>(written);
				if (stopping.load()) {
					error = "backend is stopping";
					return false;
				}
				continue;
			}
			if (written < 0 && errno == EINTR) {
				continue;
			}
			if (written < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
				pollfd descriptor{ stdinWrite, POLLOUT, 0 };
				const int pollResult = poll(&descriptor, 1, 100);
				if (pollResult < 0 && errno == EINTR) continue;
				if (stopping.load()) {
					error = "backend is stopping";
					return false;
				}
				if (pollResult > 0 && (descriptor.revents & POLLOUT) != 0) continue;
				if (pollResult == 0) continue;
				if (pollResult > 0) {
					error = "backend stdin closed while waiting to write";
					return false;
				}
			}

			error = std::strerror(errno);
			return false;
		}
		return true;
	}

	bool IsRunning() const override {
		return running.load();
	}

	void Shutdown() override {
		std::lock_guard<std::mutex> shutdownLock(shutdownMutex);

		const bool hasResources = pid > 0 || stdinWrite >= 0 || stdoutRead >= 0 || stderrRead >= 0 ||
			stdoutThread.joinable() || stderrThread.joinable() || waitThread.joinable();
		if (!hasResources) {
			running.store(false);
			stopping.store(false);
			return;
		}

		stopping.store(true);

		{
			std::lock_guard<std::mutex> writeLock(writeMutex);
			CloseDescriptor(stdinWrite);
		}

		pid_t child = -1;
		pid_t group = -1;
		{
			std::lock_guard<std::mutex> lock(stateMutex);
			child = pid;
			group = processGroup;
		}

		// Signal the group even when uv has already exited; Python descendants
		// may still be alive and holding the output pipes. Give the whole group,
		// not just its leader, the configured grace period.
		const auto gracefulDeadline = std::chrono::steady_clock::now() + kGracefulShutdownTimeout;
		if (ProcessGroupExists(group)) kill(-group, SIGTERM);
		while (ProcessGroupExists(group) && std::chrono::steady_clock::now() < gracefulDeadline) {
			std::this_thread::sleep_for(std::chrono::milliseconds(20));
		}
		if (ProcessGroupExists(group)) kill(-group, SIGKILL);

		if (waitThread.joinable()) {
			waitThread.join();
		}
		else if (child > 0) {
			// Startup may fail before the wait thread is constructed. In that
			// case Shutdown must remain the child reaper.
			int status = 0;
			while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
			running.store(false);
		}

		// After the group exits, allow readers a bounded interval to consume
		// buffered output and observe EOF. Only cancel them if an escaped
		// descendant retained a pipe.
		{
			std::unique_lock<std::mutex> lock(stateMutex);
			stateChanged.wait_for(lock, std::chrono::milliseconds(250), [this] {
				return (!stdoutThread.joinable() || stdoutDone.load()) &&
					(!stderrThread.joinable() || stderrDone.load());
			});
		}
		stopReaders.store(true);
		if (stdoutThread.joinable()) stdoutThread.join();
		if (stderrThread.joinable()) stderrThread.join();

		CloseDescriptor(stdoutRead);
		CloseDescriptor(stderrRead);

		{
			std::lock_guard<std::mutex> lock(stateMutex);
			pid = -1;
			processGroup = -1;
			running.store(false);
			stopping.store(false);
			stopReaders.store(false);
		}
	}

private:
	static void CloseAll(
		std::array<int, 2>& stdinPipe,
		std::array<int, 2>& stdoutPipe,
		std::array<int, 2>& stderrPipe) {
		CloseDescriptor(stdinPipe[0]);
		CloseDescriptor(stdinPipe[1]);
		CloseDescriptor(stdoutPipe[0]);
		CloseDescriptor(stdoutPipe[1]);
		CloseDescriptor(stderrPipe[0]);
		CloseDescriptor(stderrPipe[1]);
	}

	void ReaderThread(
		int descriptor,
		LineHandler handler,
		std::atomic<bool>* completionFlag) {
		ReadLoop(descriptor, std::move(handler));
		completionFlag->store(true);
		ReleaseCompletedProcessGroup();
		stateChanged.notify_all();
	}

	void ReadLoop(int descriptor, LineHandler handler) {
		std::string pending;
		std::array<char, kReadBufferSize> buffer{};
		bool reachedEof = false;

		while (!stopReaders.load()) {
			pollfd pollDescriptor{ descriptor, POLLIN, 0 };
			const int pollResult = poll(&pollDescriptor, 1, 100);
			if (pollResult < 0) {
				if (errno == EINTR) continue;
				break;
			}
			if (pollResult == 0) continue;
			if ((pollDescriptor.revents & (POLLIN | POLLHUP)) == 0) break;

			const ssize_t count = read(descriptor, buffer.data(), buffer.size());
			if (count > 0) {
				pending.append(buffer.data(), static_cast<std::size_t>(count));
				EmitCompleteLines(pending, handler);
				if (pending.size() > kMaximumLineSize) {
					pending.clear();
				}
				continue;
			}
			if (count == 0) {
				reachedEof = true;
				break;
			}
			if (errno == EINTR) continue;
			break;
		}

		if (reachedEof && !pending.empty()) {
			if (pending.back() == '\r') pending.pop_back();
			handler(std::move(pending));
		}
	}

	static void EmitCompleteLines(std::string& pending, const LineHandler& handler) {
		std::size_t newline = 0;
		while ((newline = pending.find('\n')) != std::string::npos) {
			std::string line = pending.substr(0, newline);
			pending.erase(0, newline + 1);
			if (!line.empty() && line.back() == '\r') line.pop_back();
			handler(std::move(line));
		}
	}

	void WaitLoop(pid_t childPid) {
		int status = 0;
		while (waitpid(childPid, &status, 0) < 0) {
			if (errno != EINTR) break;
		}
		running.store(false);
		ReleaseCompletedProcessGroup();
		stateChanged.notify_all();
	}

	void ReleaseCompletedProcessGroup() {
		std::lock_guard<std::mutex> lock(stateMutex);
		if (!running.load() && stdoutDone.load() && stderrDone.load() &&
			!ProcessGroupExists(processGroup)) {
			processGroup = -1;
		}
	}

	std::atomic<bool> running{ false };
	std::atomic<bool> stopping{ false };
	std::atomic<bool> stopReaders{ false };
	std::atomic<bool> stdoutDone{ true };
	std::atomic<bool> stderrDone{ true };

	mutable std::mutex stateMutex;
	std::mutex shutdownMutex;
	std::mutex writeMutex;
	std::condition_variable stateChanged;

	pid_t pid = -1;
	pid_t processGroup = -1;
	int stdinWrite = -1;
	int stdoutRead = -1;
	int stderrRead = -1;

	LineHandler stdoutLineHandler;
	LineHandler stderrLineHandler;
	std::thread stdoutThread;
	std::thread stderrThread;
	std::thread waitThread;
};

} // namespace

std::unique_ptr<IPCClientPlatform> CreateIPCClientPlatform() {
	return std::make_unique<PosixIPCClientPlatform>();
}

#endif
