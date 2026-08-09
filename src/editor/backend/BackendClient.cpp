#include "editor/backend/BackendClient.h"

#include <utility>

BackendClient::BackendClient(BackendConfig config)
    : config_(std::move(config)) {}

BackendClient::~BackendClient() {
    Stop();
}

// Ensures any existing process and background reader threads are terminated,
// clears event queues, and launches the backend process with fresh threads.
bool BackendClient::Start() {
    Stop();

    if (!process_.Start(config_.executable, config_.arguments, config_.workingDirectory)) {
        return false;
    }

    {
        std::scoped_lock lock(messageMutex_);
        messages_.clear();
    }
    {
        std::scoped_lock lock(diagnosticMutex_);
        diagnostics_.clear();
    }

    // Mark active state and spawn asynchronous stdout/stderr reader threads
    stopping_ = false;
    try {
        stdoutReader_ = std::thread(&BackendClient::ReadStdout, this);
        stderrReader_ = std::thread(&BackendClient::ReadStderr, this);
    } catch (...) {
        stopping_ = true;
        process_.Stop();
        if (stdoutReader_.joinable()) {
            stdoutReader_.join();
        }
        if (stderrReader_.joinable()) {
            stderrReader_.join();
        }
        return false;
    }

    return true;
}

// Signals reader threads to exit, terminates the child process, and waits for threads to join.
void BackendClient::Stop() {
    stopping_ = true;
    process_.Stop();
    if (stdoutReader_.joinable()) {
        stdoutReader_.join();
    }
    if (stderrReader_.joinable()) {
        stderrReader_.join();
    }
}

bool BackendClient::Send(std::string_view message) {
    return process_.WriteLine(message);
}

// Drains pending backend events in constant O(1) time via vector swapping under lock.
std::vector<std::string> BackendClient::PollMessages() {
    std::vector<std::string> messages;
    {
        std::scoped_lock lock(messageMutex_);
        messages.swap(messages_);
    }
    return messages;
}

// Drains pending diagnostic logs in constant O(1) time via vector swapping under lock.
std::vector<std::string> BackendClient::PollDiagnostics() {
    std::vector<std::string> diagnostics;
    {
        std::scoped_lock lock(diagnosticMutex_);
        diagnostics.swap(diagnostics_);
    }
    return diagnostics;
}

// Background thread loop: continuously reads stdout, parses events, and queues them.
void BackendClient::ReadStdout() {
    std::string line;
    while (process_.ReadStdoutLine(line)) {
        if (line.empty()) {
            continue;
        }

        std::scoped_lock lock(messageMutex_);
        messages_.push_back(std::move(line));
    }
}

// Background thread loop: continuously reads stderr and queues raw diagnostic messages.
void BackendClient::ReadStderr() {
    std::string line;
    while (process_.ReadStderrLine(line)) {
        if (line.empty()) {
            continue;
        }

        std::scoped_lock lock(diagnosticMutex_);
        diagnostics_.push_back(std::move(line));
    }
}
