#include "editor/backend/BackendClient.h"

#include <utility>

BackendClient::BackendClient(BackendConfig config)
    : config_(std::move(config)) {}

BackendClient::~BackendClient() {
    Stop();
}

// Launches the process using the internally stored BackendConfig.
bool BackendClient::Start() {
    return Start(config_.executable, config_.arguments, config_.workingDirectory);
}

// Ensures any existing process and background reader threads are terminated,
// clears event queues, and launches the backend process with fresh threads.
bool BackendClient::Start(const std::filesystem::path& executable,
                           const std::vector<std::string>& arguments,
                           const std::filesystem::path& workingDirectory) {
    Stop();

    if (!process_.Start(executable, arguments, workingDirectory)) {
        return false;
    }

    {
        std::scoped_lock lock(eventMutex_);
        events_.clear();
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

bool BackendClient::IsRunning() {
    return process_.IsRunning();
}

bool BackendClient::StartRun(const StartRunCommand& command) {
    return process_.WriteLine(SerializeCommand(command));
}

bool BackendClient::SubmitSelection(const SubmitSelectionCommand& command) {
    return process_.WriteLine(SerializeCommand(command));
}

bool BackendClient::CancelRun(const CancelRunCommand& command) {
    return process_.WriteLine(SerializeCommand(command));
}

bool BackendClient::AdvanceRun(const AdvanceRunCommand& command) {
    return process_.WriteLine(SerializeCommand(command));
}

// Drains pending backend events in constant O(1) time via vector swapping under lock.
std::vector<BackendEvent> BackendClient::PollEvents() {
    std::vector<BackendEvent> events;
    {
        std::scoped_lock lock(eventMutex_);
        events.swap(events_);
    }
    return events;
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

        auto event = ParseEvent(line);
        if (event) {
            std::scoped_lock lock(eventMutex_);
            events_.push_back(std::move(*event));
        } else {
            std::scoped_lock lock(diagnosticMutex_);
            diagnostics_.push_back(std::move(line));
        }
    }

    // Push a disconnect event if the process died unexpectedly without Stop() being called
    if (!stopping_) {
        std::scoped_lock lock(eventMutex_);
        events_.push_back(BackendDisconnectedEvent{"Backend process disconnected"});
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
