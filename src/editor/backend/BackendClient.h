#pragma once

#include "editor/backend/BackendConfig.h"
#include "editor/backend/BackendProcess.h"

#include <atomic>
#include <mutex>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

/// Manages the external backend process and communicates via non-blocking IPC.
/// Because this class manages worker threads, mutexes, and process handles,
/// prefer storing instances via std::unique_ptr (or keeping them at a fixed memory location)
/// to maintain pointer stability.
class BackendClient {
public:
    explicit BackendClient(BackendConfig config);
    ~BackendClient();

    BackendClient(const BackendClient&) = delete;
    BackendClient& operator=(const BackendClient&) = delete;

    bool Start();
    void Stop();

    bool Send(std::string_view message);

    std::vector<std::string> PollMessages();
    std::vector<std::string> PollDiagnostics();

private:
    void ReadStdout();
    void ReadStderr();

    BackendConfig config_;

    BackendProcess process_;
    std::thread stdoutReader_;
    std::thread stderrReader_;

    std::mutex messageMutex_;
    std::vector<std::string> messages_;

    std::mutex diagnosticMutex_;
    std::vector<std::string> diagnostics_;

    std::atomic<bool> stopping_{true};
};
