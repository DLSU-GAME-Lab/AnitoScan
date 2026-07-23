#pragma once
#include <memory>
#include <vector>
#include "../state/EditorState.h"
#include "../IPCClient.h"

class PipelineController {
public:
    PipelineController(EditorState& state, IPCClient& ipc);

    // Backend Lifecycle
    void StartBackend(const std::string& executable, const std::vector<std::string>& arguments);
    void StopBackend();
    void RestartBackend();

    // Pipeline Commands
    void StartRun(const std::string& runName, const std::string& input, int minFrames, const std::string& quality);
    void CancelRun();
    void SubmitSelection(const std::string& requestId, int choice);
    void SkipSelection(const std::string& requestId);

    // Main thread tick
    void Tick();

private:
    EditorState& state;
    IPCClient& ipc;
};
