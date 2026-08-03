#pragma once

#include "editor/backend/BackendConfig.h"
#include "editor/backend/BackendProcess.h"
#include "editor/backend/BackendProtocol.h"

#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

class BackendClient {
public:
    BackendClient() = default;
    ~BackendClient();

    BackendClient(const BackendClient&) = delete;
    BackendClient& operator=(const BackendClient&) = delete;

    bool Start(const BackendConfig& config);
    void Stop();
    bool IsRunning();

    bool StartRun(const StartRunCommand& command);
    bool SubmitSelection(const SubmitSelectionCommand& command);
    bool CancelRun(const CancelRunCommand& command);

    std::vector<BackendEvent> PollEvents();
    std::vector<std::string> PollDiagnostics();

private:
    void ReadStdout();
    void ReadStderr();

    BackendProcess process_;
    std::thread stdoutReader_;
    std::thread stderrReader_;
    std::mutex eventMutex_;
    std::deque<BackendEvent> events_;
    std::mutex diagnosticMutex_;
    std::deque<std::string> diagnostics_;
};
