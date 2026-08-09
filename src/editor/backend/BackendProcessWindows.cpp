#define NOMINMAX
#include <Windows.h>

#include "editor/backend/BackendProcess.h"

#include <mutex>
#include <string>
#include <utility>
#include <vector>

struct BackendProcess::Impl {
    HANDLE process_ = nullptr;
    HANDLE job_ = nullptr;
    HANDLE stdinWrite_ = nullptr;
    HANDLE stdoutRead_ = nullptr;
    HANDLE stderrRead_ = nullptr;
    std::mutex stdoutMutex_;
    std::mutex stderrMutex_;
    std::string stdoutBuffer_;
    std::string stderrBuffer_;
};

namespace {

void CloseHandleIfSet(HANDLE& handle) {
    if (handle) {
        CloseHandle(handle);
        handle = nullptr;
    }
}

std::wstring Utf8ToWide(std::string_view value) {
    if (value.empty()) {
        return {};
    }
    const int size = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(),
                                         static_cast<int>(value.size()), nullptr, 0);
    if (size <= 0) {
        return {};
    }
    std::wstring result(static_cast<std::size_t>(size), L'\0');
    if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(),
                            static_cast<int>(value.size()), result.data(), size) != size) {
        return {};
    }
    return result;
}

std::wstring QuoteArgument(const std::wstring& argument) {
    if (argument.find_first_of(L" \t\n\v\"") == std::wstring::npos) {
        return argument;
    }
    std::wstring quoted(1, L'"');
    std::size_t backslashes = 0;
    for (wchar_t character : argument) {
        if (character == L'\\') {
            ++backslashes;
        } else if (character == L'"') {
            quoted.append(backslashes * 2 + 1, L'\\');
            quoted.push_back(L'"');
            backslashes = 0;
        } else {
            quoted.append(backslashes, L'\\');
            backslashes = 0;
            quoted.push_back(character);
        }
    }
    quoted.append(backslashes * 2, L'\\');
    quoted.push_back(L'"');
    return quoted;
}

bool ReadLine(HANDLE handle, std::string& buffer, std::string& line) {
    line.clear();
    for (;;) {
        const std::size_t newline = buffer.find('\n');
        if (newline != std::string::npos) {
            line.assign(buffer, 0, newline);
            buffer.erase(0, newline + 1);
            return true;
        }
        char data[4096];
        DWORD count = 0;
        if (ReadFile(handle, data, sizeof(data), &count, nullptr) && count > 0) {
            buffer.append(data, count);
            continue;
        }
        if (!buffer.empty()) {
            line = std::move(buffer);
            buffer.clear();
            return true;
        }
        return false;
    }
}

} // namespace

BackendProcess::BackendProcess() : impl_(std::make_unique<Impl>()) {}

BackendProcess::~BackendProcess() {
    Stop();
}

bool BackendProcess::Start(const std::filesystem::path& executable,
                           const std::vector<std::string>& arguments,
                           const std::filesystem::path& workingDirectory) {
    Stop();

    SECURITY_ATTRIBUTES security {sizeof(security), nullptr, TRUE};
    HANDLE stdinRead = nullptr;
    HANDLE stdoutRead = nullptr;
    HANDLE stdoutWrite = nullptr;
    HANDLE stderrRead = nullptr;
    HANDLE stderrWrite = nullptr;
    if (!CreatePipe(&stdinRead, &impl_->stdinWrite_, &security, 0) ||
        !CreatePipe(&stdoutRead, &stdoutWrite, &security, 0) ||
        !CreatePipe(&stderrRead, &stderrWrite, &security, 0) ||
        !SetHandleInformation(impl_->stdinWrite_, HANDLE_FLAG_INHERIT, 0) ||
        !SetHandleInformation(stdoutRead, HANDLE_FLAG_INHERIT, 0) ||
        !SetHandleInformation(stderrRead, HANDLE_FLAG_INHERIT, 0)) {
        CloseHandleIfSet(stdinRead);
        CloseHandleIfSet(stdoutRead);
        CloseHandleIfSet(stdoutWrite);
        CloseHandleIfSet(stderrRead);
        CloseHandleIfSet(stderrWrite);
        Stop();
        return false;
    }

    impl_->job_ = CreateJobObjectW(nullptr, nullptr);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits {};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!impl_->job_ || !SetInformationJobObject(impl_->job_, JobObjectExtendedLimitInformation,
                                                  &limits, sizeof(limits))) {
        CloseHandleIfSet(stdinRead);
        CloseHandleIfSet(stdoutRead);
        CloseHandleIfSet(stdoutWrite);
        CloseHandleIfSet(stderrRead);
        CloseHandleIfSet(stderrWrite);
        Stop();
        return false;
    }

    std::wstring commandLine = QuoteArgument(executable.native());
    for (const std::string& argument : arguments) {
        std::wstring wideArgument = Utf8ToWide(argument);
        if (!argument.empty() && wideArgument.empty()) {
            CloseHandleIfSet(stdinRead);
            CloseHandleIfSet(stdoutRead);
            CloseHandleIfSet(stdoutWrite);
            CloseHandleIfSet(stderrRead);
            CloseHandleIfSet(stderrWrite);
            Stop();
            return false;
        }
        commandLine.push_back(L' ');
        commandLine += QuoteArgument(wideArgument);
    }
    std::vector<wchar_t> mutableCommandLine(commandLine.begin(), commandLine.end());
    mutableCommandLine.push_back(L'\0');

    STARTUPINFOW startup {};
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = stdinRead;
    startup.hStdOutput = stdoutWrite;
    startup.hStdError = stderrWrite;
    PROCESS_INFORMATION processInfo {};
    const wchar_t* directory = workingDirectory.empty() ? nullptr : workingDirectory.c_str();
    const BOOL created = CreateProcessW(executable.c_str(), mutableCommandLine.data(), nullptr, nullptr,
                                        TRUE, CREATE_NO_WINDOW | CREATE_SUSPENDED, nullptr, directory,
                                        &startup, &processInfo);
    CloseHandleIfSet(stdinRead);
    CloseHandleIfSet(stdoutWrite);
    CloseHandleIfSet(stderrWrite);
    if (!created) {
        CloseHandleIfSet(stdoutRead);
        CloseHandleIfSet(stderrRead);
        Stop();
        return false;
    }

    impl_->process_ = processInfo.hProcess;
    if (!AssignProcessToJobObject(impl_->job_, impl_->process_)) {
        TerminateProcess(impl_->process_, 1);
        CloseHandle(processInfo.hThread);
        CloseHandleIfSet(stdoutRead);
        CloseHandleIfSet(stderrRead);
        Stop();
        return false;
    }
    {
        std::scoped_lock lock(impl_->stdoutMutex_);
        impl_->stdoutRead_ = stdoutRead;
        stdoutRead = nullptr;
        impl_->stdoutBuffer_.clear();
    }
    {
        std::scoped_lock lock(impl_->stderrMutex_);
        impl_->stderrRead_ = stderrRead;
        stderrRead = nullptr;
        impl_->stderrBuffer_.clear();
    }
    if (ResumeThread(processInfo.hThread) == static_cast<DWORD>(-1)) {
        TerminateJobObject(impl_->job_, 1);
        CloseHandle(processInfo.hThread);
        Stop();
        return false;
    }
    CloseHandle(processInfo.hThread);
    return true;
}

void BackendProcess::Stop() {
    CloseHandleIfSet(impl_->stdinWrite_);
    if (impl_->job_) {
        TerminateJobObject(impl_->job_, 1);
    } else if (impl_->process_) {
        TerminateProcess(impl_->process_, 1);
    }
    if (impl_->process_) {
        WaitForSingleObject(impl_->process_, 1000);
    }
    {
        std::scoped_lock lock(impl_->stdoutMutex_);
        CloseHandleIfSet(impl_->stdoutRead_);
        impl_->stdoutBuffer_.clear();
    }
    {
        std::scoped_lock lock(impl_->stderrMutex_);
        CloseHandleIfSet(impl_->stderrRead_);
        impl_->stderrBuffer_.clear();
    }
    CloseHandleIfSet(impl_->process_);
    CloseHandleIfSet(impl_->job_);
}

bool BackendProcess::WriteLine(std::string_view line) {
    if (!impl_->stdinWrite_) {
        return false;
    }
    std::string framed(line);
    framed.push_back('\n');
    std::size_t offset = 0;
    while (offset < framed.size()) {
        DWORD written = 0;
        const DWORD remaining = static_cast<DWORD>(framed.size() - offset);
        if (!WriteFile(impl_->stdinWrite_, framed.data() + offset, remaining, &written, nullptr) || written == 0) {
            return false;
        }
        offset += written;
    }
    return true;
}

bool BackendProcess::ReadStdoutLine(std::string& line) {
    std::scoped_lock lock(impl_->stdoutMutex_);
    return impl_->stdoutRead_ && ReadLine(impl_->stdoutRead_, impl_->stdoutBuffer_, line);
}

bool BackendProcess::ReadStderrLine(std::string& line) {
    std::scoped_lock lock(impl_->stderrMutex_);
    return impl_->stderrRead_ && ReadLine(impl_->stderrRead_, impl_->stderrBuffer_, line);
}
