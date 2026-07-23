#pragma once
#include <memory>
#include <vector>
#include "../state/EditorState.h"
#include "../IPCClient.h"

class PipelineController {
public:
    PipelineController(EditorState& state, IPCClient& ipc);

    // Main thread API invoked by UI
    void StartRun(const std::string& runName, const std::string& input, int minFrames, const std::string& quality);
    void CancelRun();
    void SubmitSelection(const std::string& requestId, int choice);
    void SkipSelection(const std::string& requestId);

    // Processes IPC messages and mutates EditorState
    void Tick();

private:
    void HandleDecodedEvent(const IPCProtocol::DecodedEvent& event);

    EditorState& state;
    IPCClient& ipc;
    bool wasBackendRunning = false;
};
