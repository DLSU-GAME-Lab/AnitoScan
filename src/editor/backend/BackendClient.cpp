#include "editor/backend/BackendClient.h"

#include <utility>

BackendClient::~BackendClient() {
    Stop();
}

bool BackendClient::Start(const BackendConfig& config) {
    if (process_.IsRunning()) {
        return false;
    }

    Stop();
    if (!process_.Start(config.executable, config.arguments, config.workingDirectory)) {
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

    try {
        stdoutReader_ = std::thread(&BackendClient::ReadStdout, this);
        stderrReader_ = std::thread(&BackendClient::ReadStderr, this);
    } catch (...) {
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

void BackendClient::Stop() {
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

std::vector<BackendEvent> BackendClient::PollEvents() {
    std::scoped_lock lock(eventMutex_);
    std::vector<BackendEvent> events;
    events.reserve(events_.size());
    while (!events_.empty()) {
        events.push_back(std::move(events_.front()));
        events_.pop_front();
    }
    return events;
}

std::vector<std::string> BackendClient::PollDiagnostics() {
    std::scoped_lock lock(diagnosticMutex_);
    std::vector<std::string> diagnostics;
    diagnostics.reserve(diagnostics_.size());
    while (!diagnostics_.empty()) {
        diagnostics.push_back(std::move(diagnostics_.front()));
        diagnostics_.pop_front();
    }
    return diagnostics;
}

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
}

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
