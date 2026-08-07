#pragma once

#include "editor/backend/BackendConfig.h"
#include "editor/backend/BackendProcess.h"
#include "editor/backend/BackendProtocol.h"

#include <atomic>
#include <mutex>
#include <string>
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

    bool Start(const std::filesystem::path& executable,
               const std::vector<std::string>& arguments,
               const std::filesystem::path& workingDirectory);

    void Stop();
    bool IsRunning();

    bool StartRun(const StartRunCommand& command);
    bool SubmitSelection(const SubmitSelectionCommand& command);
    bool CancelRun(const CancelRunCommand& command);
    bool AdvanceRun(const AdvanceRunCommand& command);

    std::vector<BackendEvent> PollEvents();
    std::vector<std::string> PollDiagnostics();

private:
    void ReadStdout();
    void ReadStderr();

    BackendConfig config_;

    BackendProcess process_;
    std::thread stdoutReader_;
    std::thread stderrReader_;

    std::mutex eventMutex_;
    std::vector<BackendEvent> events_;

    std::mutex diagnosticMutex_;
    std::vector<std::string> diagnostics_;

    std::atomic<bool> stopping_{true};
};
