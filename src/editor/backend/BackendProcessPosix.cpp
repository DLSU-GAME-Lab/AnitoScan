#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif

#include "editor/backend/BackendProcess.h"

#include <cerrno>
#include <csignal>
#include <mutex>
#include <spawn.h>
#include <string>
#include <time.h>
#include <unistd.h>
#include <sys/wait.h>
#include <utility>
#include <vector>

extern char** environ;

struct BackendProcess::Impl {
    pid_t pid_ = -1;
    int stdinFd_ = -1;
    int stdoutFd_ = -1;
    int stderrFd_ = -1;
    std::mutex stdoutMutex_;
    std::mutex stderrMutex_;
    std::string stdoutBuffer_;
    std::string stderrBuffer_;
};

namespace {

void CloseFd(int& fd) {
    if (fd >= 0) {
        close(fd);
        fd = -1;
    }
}

void ClosePipe(int pipeFds[2]) {
    CloseFd(pipeFds[0]);
    CloseFd(pipeFds[1]);
}

bool AddDupAndClose(posix_spawn_file_actions_t& actions, int source, int destination) {
    return posix_spawn_file_actions_adddup2(&actions, source, destination) == 0 &&
           posix_spawn_file_actions_addclose(&actions, source) == 0;
}

bool ReadLine(int fd, std::string& buffer, std::string& line) {
    line.clear();
    for (;;) {
        const std::size_t newline = buffer.find('\n');
        if (newline != std::string::npos) {
            line.assign(buffer, 0, newline);
            buffer.erase(0, newline + 1);
            return true;
        }

        char data[4096];
        const ssize_t count = read(fd, data, sizeof(data));
        if (count > 0) {
            buffer.append(data, static_cast<std::size_t>(count));
            continue;
        }
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count == 0 && !buffer.empty()) {
            line = std::move(buffer);
            buffer.clear();
            return true;
        }
        return false;
    }
}

} // namespace

BackendProcess::BackendProcess() : impl_(std::make_unique<Impl>()) {
    struct sigaction action {};
    action.sa_handler = SIG_IGN;
    sigemptyset(&action.sa_mask);
    sigaction(SIGPIPE, &action, nullptr);
}

BackendProcess::~BackendProcess() {
    Stop();
}

bool BackendProcess::Start(const std::filesystem::path& executable,
                           const std::vector<std::string>& arguments,
                           const std::filesystem::path& workingDirectory) {
    Stop();

    int stdinPipe[2] {-1, -1};
    int stdoutPipe[2] {-1, -1};
    int stderrPipe[2] {-1, -1};
    if (pipe(stdinPipe) != 0 || pipe(stdoutPipe) != 0 || pipe(stderrPipe) != 0) {
        ClosePipe(stdinPipe);
        ClosePipe(stdoutPipe);
        ClosePipe(stderrPipe);
        return false;
    }

    posix_spawn_file_actions_t actions;
    posix_spawnattr_t attributes;
    bool actionsInitialized = posix_spawn_file_actions_init(&actions) == 0;
    bool attributesInitialized = posix_spawnattr_init(&attributes) == 0;
    bool configured = actionsInitialized && attributesInitialized;

    if (configured) {
        configured = AddDupAndClose(actions, stdinPipe[0], STDIN_FILENO) &&
                     AddDupAndClose(actions, stdoutPipe[1], STDOUT_FILENO) &&
                     AddDupAndClose(actions, stderrPipe[1], STDERR_FILENO) &&
                     posix_spawn_file_actions_addclose(&actions, stdinPipe[1]) == 0 &&
                     posix_spawn_file_actions_addclose(&actions, stdoutPipe[0]) == 0 &&
                     posix_spawn_file_actions_addclose(&actions, stderrPipe[0]) == 0;
    }

    if (configured && !workingDirectory.empty()) {
#if defined(__APPLE__) && defined(__MAC_OS_X_VERSION_MAX_ALLOWED) && __MAC_OS_X_VERSION_MAX_ALLOWED >= 260000
        configured = posix_spawn_file_actions_addchdir(&actions, workingDirectory.c_str()) == 0;
#elif defined(__APPLE__) || (defined(__GLIBC__) && defined(_GNU_SOURCE))
        configured = posix_spawn_file_actions_addchdir_np(&actions, workingDirectory.c_str()) == 0;
#else
        configured = false;
#endif
    }

    if (configured) {
        configured = posix_spawnattr_setflags(&attributes, POSIX_SPAWN_SETPGROUP) == 0 &&
                     posix_spawnattr_setpgroup(&attributes, 0) == 0;
    }

    std::string executableString = executable.string();
    std::vector<std::string> argumentStorage;
    argumentStorage.reserve(arguments.size() + 1);
    argumentStorage.push_back(executableString);
    argumentStorage.insert(argumentStorage.end(), arguments.begin(), arguments.end());
    std::vector<char*> argv;
    argv.reserve(argumentStorage.size() + 1);
    for (std::string& argument : argumentStorage) {
        argv.push_back(argument.data());
    }
    argv.push_back(nullptr);

    pid_t pid = -1;
    const int spawnResult = configured
        ? posix_spawnp(&pid, executableString.c_str(), &actions, &attributes, argv.data(), environ)
        : EINVAL;

    if (actionsInitialized) {
        posix_spawn_file_actions_destroy(&actions);
    }
    if (attributesInitialized) {
        posix_spawnattr_destroy(&attributes);
    }

    CloseFd(stdinPipe[0]);
    CloseFd(stdoutPipe[1]);
    CloseFd(stderrPipe[1]);
    if (spawnResult != 0) {
        CloseFd(stdinPipe[1]);
        CloseFd(stdoutPipe[0]);
        CloseFd(stderrPipe[0]);
        return false;
    }

    impl_->pid_ = pid;
    impl_->stdinFd_ = stdinPipe[1];
    {
        std::scoped_lock lock(impl_->stdoutMutex_);
        impl_->stdoutFd_ = stdoutPipe[0];
        impl_->stdoutBuffer_.clear();
    }
    {
        std::scoped_lock lock(impl_->stderrMutex_);
        impl_->stderrFd_ = stderrPipe[0];
        impl_->stderrBuffer_.clear();
    }
    return true;
}

void BackendProcess::Stop() {
    CloseFd(impl_->stdinFd_);

    if (impl_->pid_ > 0) {
        kill(-impl_->pid_, SIGTERM);
        bool reaped = false;
        for (int attempt = 0; attempt < 50; ++attempt) {
            const pid_t result = waitpid(impl_->pid_, nullptr, WNOHANG);
            if (result == impl_->pid_ || (result < 0 && errno == ECHILD)) {
                reaped = true;
                break;
            }
            if (result < 0 && errno != EINTR) {
                break;
            }
            timespec delay {0, 10'000'000};
            while (nanosleep(&delay, &delay) < 0 && errno == EINTR) {
            }
        }
        if (!reaped) {
            kill(-impl_->pid_, SIGKILL);
            while (waitpid(impl_->pid_, nullptr, 0) < 0 && errno == EINTR) {
            }
        }
        impl_->pid_ = -1;
    }

    {
        std::scoped_lock lock(impl_->stdoutMutex_);
        CloseFd(impl_->stdoutFd_);
        impl_->stdoutBuffer_.clear();
    }
    {
        std::scoped_lock lock(impl_->stderrMutex_);
        CloseFd(impl_->stderrFd_);
        impl_->stderrBuffer_.clear();
    }
}

bool BackendProcess::WriteLine(std::string_view line) {
    if (impl_->stdinFd_ < 0) {
        return false;
    }
    std::string framed(line);
    framed.push_back('\n');
    std::size_t offset = 0;
    while (offset < framed.size()) {
        const ssize_t count = write(impl_->stdinFd_, framed.data() + offset, framed.size() - offset);
        if (count > 0) {
            offset += static_cast<std::size_t>(count);
        } else if (count < 0 && errno == EINTR) {
            continue;
        } else {
            return false;
        }
    }
    return true;
}

bool BackendProcess::ReadStdoutLine(std::string& line) {
    std::scoped_lock lock(impl_->stdoutMutex_);
    return impl_->stdoutFd_ >= 0 && ReadLine(impl_->stdoutFd_, impl_->stdoutBuffer_, line);
}

bool BackendProcess::ReadStderrLine(std::string& line) {
    std::scoped_lock lock(impl_->stderrMutex_);
    return impl_->stderrFd_ >= 0 && ReadLine(impl_->stderrFd_, impl_->stderrBuffer_, line);
}
