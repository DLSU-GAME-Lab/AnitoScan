#include "IPCClientPlatform.h"

#if defined(_WIN32)

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <exception>
#include <cstdint>
#include <mutex>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

namespace {

constexpr DWORD kReadBufferSize = 4096;
constexpr auto kGracefulShutdownTimeout = std::chrono::milliseconds(250);

class UniqueHandle {
public:
	UniqueHandle() = default;
	explicit UniqueHandle(HANDLE value) : handle(value) {}
	~UniqueHandle() { Reset(); }

	UniqueHandle(const UniqueHandle&) = delete;
	UniqueHandle& operator=(const UniqueHandle&) = delete;

	UniqueHandle(UniqueHandle&& other) noexcept : handle(other.Release()) {}
	UniqueHandle& operator=(UniqueHandle&& other) noexcept {
		if (this != &other) Reset(other.Release());
		return *this;
	}

	HANDLE Get() const { return handle; }
	bool IsValid() const { return handle != nullptr && handle != INVALID_HANDLE_VALUE; }

	HANDLE Release() {
		HANDLE value = handle;
		handle = INVALID_HANDLE_VALUE;
		return value;
	}

	void Reset(HANDLE value = INVALID_HANDLE_VALUE) {
		if (IsValid()) CloseHandle(handle);
		handle = value;
	}

private:
	HANDLE handle = INVALID_HANDLE_VALUE;
};

std::wstring Utf8ToWide(std::string_view value) {
	if (value.empty()) return {};
	const int length = MultiByteToWideChar(
		CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), nullptr, 0);
	if (length <= 0) return {};
	std::wstring result(static_cast<std::size_t>(length), L'\0');
	if (MultiByteToWideChar(
			CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), static_cast<int>(value.size()), result.data(), length) <= 0) {
		return {};
	}
	return result;
}

std::string WideToUtf8(std::wstring_view value) {
	if (value.empty()) return {};
	const int length = WideCharToMultiByte(
		CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
	if (length <= 0) return {};
	std::string result(static_cast<std::size_t>(length), '\0');
	WideCharToMultiByte(
		CP_UTF8, 0, value.data(), static_cast<int>(value.size()), result.data(), length, nullptr, nullptr);
	return result;
}

std::string WindowsError(DWORD code = GetLastError()) {
	wchar_t* buffer = nullptr;
	const DWORD size = FormatMessageW(
		FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
		nullptr,
		code,
		MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
		reinterpret_cast<wchar_t*>(&buffer),
		0,
		nullptr);
	std::wstring message = size > 0 ? std::wstring(buffer, size) : L"unknown Windows error";
	if (buffer) LocalFree(buffer);
	while (!message.empty() && (message.back() == L'\r' || message.back() == L'\n')) message.pop_back();
	return WideToUtf8(message) + " (" + std::to_string(code) + ")";
}

std::wstring QuoteArgument(const std::wstring& argument) {
	const bool needsQuotes = argument.empty() || argument.find_first_of(L" \t\"") != std::wstring::npos;
	if (!needsQuotes) return argument;

	std::wstring quoted = L"\"";
	std::size_t backslashes = 0;
	for (wchar_t character : argument) {
		if (character == L'\\') {
			++backslashes;
			continue;
		}
		if (character == L'\"') {
			quoted.append(backslashes * 2 + 1, L'\\');
			quoted.push_back(L'\"');
			backslashes = 0;
			continue;
		}
		quoted.append(backslashes, L'\\');
		backslashes = 0;
		quoted.push_back(character);
	}
	quoted.append(backslashes * 2, L'\\');
	quoted.push_back(L'\"');
	return quoted;
}

bool BuildCommandLine(
	const std::string& executable,
	const std::vector<std::string>& arguments,
	std::vector<wchar_t>& commandLine,
	std::string& error) {
	std::vector<std::wstring> wideArguments;
	wideArguments.reserve(arguments.size() + 1);
	wideArguments.push_back(Utf8ToWide(executable));
	if (wideArguments.front().empty()) {
		error = "failed to convert executable to UTF-16";
		return false;
	}
	for (const std::string& argument : arguments) {
		std::wstring wide = Utf8ToWide(argument);
		if (!argument.empty() && wide.empty()) {
			error = "failed to convert a process argument to UTF-16";
			return false;
		}
		wideArguments.push_back(std::move(wide));
	}

	std::wstring combined;
	for (std::size_t index = 0; index < wideArguments.size(); ++index) {
		if (index > 0) combined.push_back(L' ');
		combined += QuoteArgument(wideArguments[index]);
	}
	commandLine.assign(combined.begin(), combined.end());
	commandLine.push_back(L'\0');
	return true;
}

bool CreateRedirectedPipe(UniqueHandle& parentEnd, UniqueHandle& childEnd, bool childReads, std::string& error) {
	SECURITY_ATTRIBUTES attributes{};
	attributes.nLength = sizeof(attributes);
	attributes.bInheritHandle = TRUE;

	HANDLE readHandle = INVALID_HANDLE_VALUE;
	HANDLE writeHandle = INVALID_HANDLE_VALUE;
	if (!CreatePipe(&readHandle, &writeHandle, &attributes, 0)) {
		error = WindowsError();
		return false;
	}

	UniqueHandle read(readHandle);
	UniqueHandle write(writeHandle);
	HANDLE nonInherited = childReads ? write.Get() : read.Get();
	if (!SetHandleInformation(nonInherited, HANDLE_FLAG_INHERIT, 0)) {
		error = WindowsError();
		return false;
	}

	if (childReads) {
		childEnd = std::move(read);
		parentEnd = std::move(write);
	}
	else {
		parentEnd = std::move(read);
		childEnd = std::move(write);
	}
	return true;
}

class Win32IPCClientPlatform final : public IPCClientPlatform {
public:
	~Win32IPCClientPlatform() override {
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

		std::vector<wchar_t> commandLine;
		if (!BuildCommandLine(executable, arguments, commandLine, error)) return false;

		UniqueHandle parentStdin;
		UniqueHandle childStdin;
		UniqueHandle parentStdout;
		UniqueHandle childStdout;
		UniqueHandle parentStderr;
		UniqueHandle childStderr;
		if (!CreateRedirectedPipe(parentStdin, childStdin, true, error) ||
			!CreateRedirectedPipe(parentStdout, childStdout, false, error) ||
			!CreateRedirectedPipe(parentStderr, childStderr, false, error)) {
			return false;
		}

		UniqueHandle newJob(CreateJobObjectW(nullptr, nullptr));
		if (!newJob.IsValid()) {
			error = WindowsError();
			return false;
		}
		JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
		limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
		if (!SetInformationJobObject(newJob.Get(), JobObjectExtendedLimitInformation, &limits, sizeof(limits))) {
			error = WindowsError();
			return false;
		}

		std::array<HANDLE, 3> inheritedHandles{ childStdin.Get(), childStdout.Get(), childStderr.Get() };
		SIZE_T attributeBytes = 0;
		InitializeProcThreadAttributeList(nullptr, 1, 0, &attributeBytes);
		if (GetLastError() != ERROR_INSUFFICIENT_BUFFER) {
			error = WindowsError();
			return false;
		}
		std::vector<std::byte> attributeStorage(attributeBytes);
		auto* attributeList = reinterpret_cast<PPROC_THREAD_ATTRIBUTE_LIST>(attributeStorage.data());
		if (!InitializeProcThreadAttributeList(attributeList, 1, 0, &attributeBytes)) {
			error = WindowsError();
			return false;
		}
		struct AttributeGuard {
			PPROC_THREAD_ATTRIBUTE_LIST value;
			~AttributeGuard() { DeleteProcThreadAttributeList(value); }
		} attributeGuard{ attributeList };

		if (!UpdateProcThreadAttribute(
			attributeList,
			0,
			PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
			inheritedHandles.data(),
			inheritedHandles.size() * sizeof(HANDLE),
			nullptr,
			nullptr)) {
			error = WindowsError();
			return false;
		}

		STARTUPINFOEXW startup{};
		startup.StartupInfo.cb = sizeof(startup);
		startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
		startup.StartupInfo.hStdInput = childStdin.Get();
		startup.StartupInfo.hStdOutput = childStdout.Get();
		startup.StartupInfo.hStdError = childStderr.Get();
		startup.lpAttributeList = attributeList;

		PROCESS_INFORMATION processInfo{};
		const DWORD creationFlags = CREATE_SUSPENDED | CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT;
		if (!CreateProcessW(
			nullptr,
			commandLine.data(),
			nullptr,
			nullptr,
			TRUE,
			creationFlags,
			nullptr,
			nullptr,
			&startup.StartupInfo,
			&processInfo)) {
			error = WindowsError();
			return false;
		}

		UniqueHandle newProcess(processInfo.hProcess);
		UniqueHandle primaryThread(processInfo.hThread);
		childStdin.Reset();
		childStdout.Reset();
		childStderr.Reset();

		if (!AssignProcessToJobObject(newJob.Get(), newProcess.Get())) {
			error = WindowsError();
			TerminateProcess(newProcess.Get(), 1);
			WaitForSingleObject(newProcess.Get(), INFINITE);
			return false;
		}

		{
			std::lock_guard<std::mutex> lock(stateMutex);
			job = std::move(newJob);
			process = std::move(newProcess);
			stdinWrite = std::move(parentStdin);
			stdoutRead = std::move(parentStdout);
			stderrRead = std::move(parentStderr);
			stdoutLineHandler = std::move(stdoutHandler);
			stderrLineHandler = std::move(stderrHandler);
			stopping.store(false);
			running.store(true);
		}

		try {
			// The wait thread owns process completion. Start it first so later
			// worker-construction failures still have a process owner.
			waitThread = std::thread(&Win32IPCClientPlatform::WaitLoop, this, process.Get());
			stdoutThread = std::thread(&Win32IPCClientPlatform::ReadLoop, this, stdoutRead.Get(), stdoutLineHandler);
			stderrThread = std::thread(&Win32IPCClientPlatform::ReadLoop, this, stderrRead.Get(), stderrLineHandler);
		}
		catch (const std::exception& exception) {
			error = exception.what();
			TerminateJobObject(job.Get(), 1);
			Shutdown();
			return false;
		}

		if (ResumeThread(primaryThread.Get()) == static_cast<DWORD>(-1)) {
			error = WindowsError();
			TerminateJobObject(job.Get(), 1);
			Shutdown();
			return false;
		}
		return true;
	}

	bool Send(std::string_view data, std::string& error) override {
		std::lock_guard<std::timed_mutex> lock(writeMutex);
		if (!running.load() || stopping.load() || !stdinWrite.IsValid()) {
			error = "backend stdin is not available";
			return false;
		}

		std::size_t offset = 0;
		while (offset < data.size()) {
			const DWORD chunk = static_cast<DWORD>(
				(data.size() - offset) > MAXDWORD ? MAXDWORD : (data.size() - offset));
			DWORD written = 0;
			if (!WriteFile(stdinWrite.Get(), data.data() + offset, chunk, &written, nullptr)) {
				error = WindowsError();
				return false;
			}
			if (written == 0) {
				error = "WriteFile completed without making progress";
				return false;
			}
			offset += written;
		}
		return true;
	}

	bool IsRunning() const override {
		return running.load();
	}

	void Shutdown() override {
		std::lock_guard<std::mutex> shutdownLock(shutdownMutex);
		const bool hasResources = process.IsValid() || job.IsValid() || stdinWrite.IsValid() ||
			stdoutRead.IsValid() || stderrRead.IsValid() || stdoutThread.joinable() ||
			stderrThread.joinable() || waitThread.joinable();
		if (!hasResources) {
			running.store(false);
			stopping.store(false);
			return;
		}

		stopping.store(true);
		bool forced = false;
		std::unique_lock<std::timed_mutex> writeLock(writeMutex, std::defer_lock);
		if (writeLock.try_lock_for(std::chrono::milliseconds(50))) {
			stdinWrite.Reset();
		}
		else {
			// Closing the kill-on-close job forces a blocked WriteFile to return
			// before waiting indefinitely on its mutex.
			job.Reset();
			forced = true;
			writeLock.lock();
			stdinWrite.Reset();
		}
		writeLock.unlock();

		if (!forced) {
			std::unique_lock<std::mutex> lock(stateMutex);
			stateChanged.wait_for(lock, kGracefulShutdownTimeout, [this] { return !running.load(); });
		}

		// Closing the configured job kills any descendants that outlived the
		// direct uv process and releases their inherited pipe writers.
		job.Reset();

		if (!waitThread.joinable() && process.IsValid()) {
			const DWORD waitResult = WaitForSingleObject(process.Get(), INFINITE);
			if (waitResult == WAIT_OBJECT_0) running.store(false);
		}
		if (waitThread.joinable()) waitThread.join();

		if (stdoutThread.joinable()) {
			CancelSynchronousIo(stdoutThread.native_handle());
			stdoutThread.join();
		}
		if (stderrThread.joinable()) {
			CancelSynchronousIo(stderrThread.native_handle());
			stderrThread.join();
		}

		stdoutRead.Reset();
		stderrRead.Reset();
		process.Reset();
		running.store(false);
		stopping.store(false);
	}

private:
	void ReadLoop(HANDLE descriptor, LineHandler handler) {
		std::array<char, kReadBufferSize> buffer{};
		std::string pending;
		while (true) {
			DWORD count = 0;
			if (!ReadFile(descriptor, buffer.data(), static_cast<DWORD>(buffer.size()), &count, nullptr) || count == 0) {
				break;
			}
			pending.append(buffer.data(), count);
			EmitCompleteLines(pending, handler);
		}
		if (!pending.empty()) {
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

	void WaitLoop(HANDLE processHandle) {
		const DWORD result = WaitForSingleObject(processHandle, INFINITE);
		if (result == WAIT_OBJECT_0) {
			running.store(false);
		}
		stateChanged.notify_all();
	}

	std::atomic<bool> running{ false };
	std::atomic<bool> stopping{ false };
	mutable std::mutex stateMutex;
	std::mutex shutdownMutex;
	std::timed_mutex writeMutex;
	std::condition_variable stateChanged;

	UniqueHandle job;
	UniqueHandle process;
	UniqueHandle stdinWrite;
	UniqueHandle stdoutRead;
	UniqueHandle stderrRead;

	LineHandler stdoutLineHandler;
	LineHandler stderrLineHandler;
	std::thread stdoutThread;
	std::thread stderrThread;
	std::thread waitThread;
};

} // namespace

std::unique_ptr<IPCClientPlatform> CreateIPCClientPlatform() {
	return std::make_unique<Win32IPCClientPlatform>();
}

#endif
