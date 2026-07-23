#include "PipelineController.h"
#include "../IPCProtocol.h"
#include <iostream>

PipelineController::PipelineController(EditorState& state, IPCClient& ipc)
    : state(state), ipc(ipc) {}

void PipelineController::StartRun(const std::string& runName, const std::string& input, int minFrames, const std::string& quality) {
    if (!ipc.IsBackendReady()) return;

    state.pipeline.runState = RunState::STARTING;
    state.pipeline.runName = runName;
    state.pipeline.activePhase = Phase::NONE;
    state.pipeline.phaseProgress = 0.0f;
    state.pipeline.overallProgress = 0.0f;
    state.pipeline.latestOutput.clear();

    std::string cmd = IPCProtocol::SerializeRunPipeline(runName, input, minFrames, quality);
    ipc.Send(cmd);
}

void PipelineController::CancelRun() {
    if (state.pipeline.runState == RunState::IDLE) return;
    std::string cmd = IPCProtocol::SerializeCancelPipeline(state.pipeline.runName);
    ipc.Send(cmd);
    state.pipeline.runState = RunState::CANCELLED;
}

void PipelineController::SubmitSelection(const std::string& requestId, int choice) {
    ipc.Send(IPCProtocol::SerializeSelection(requestId, choice));
    state.pipeline.runState = RunState::RUNNING; // Assume running until backend confirms
}

void PipelineController::SkipSelection(const std::string& requestId) {
    ipc.Send(IPCProtocol::SerializeSelectionSkip(requestId));
    state.pipeline.runState = RunState::RUNNING;
}

void PipelineController::Tick() {
    std::vector<BackendMessage> messages;
    ipc.Poll(messages);

    // Detect unexpected process exit
    bool isRunning = ipc.IsRunning();
    if (wasBackendRunning && !isRunning && state.pipeline.runState != RunState::IDLE && state.pipeline.runState != RunState::COMPLETED) {
        state.pipeline.runState = RunState::FAILED;
        state.pipeline.lastErrorMessage = "Backend process terminated unexpectedly.";
        state.logQueue.push_back("[CRITICAL] Backend process terminated unexpectedly.");
    }
    wasBackendRunning = isRunning;

    for (const auto& msg : messages) {
        IPCProtocol::DecodedEvent event = IPCProtocol::DecodeEvent(msg.raw);

        switch (event.type) {
            case IPCProtocol::EventType::BACKEND_READY:
                if (event.backendReady.protocolVersion != IPCProtocol::PROTOCOL_VERSION) {
                    state.logQueue.push_back("[ERROR] Backend protocol version mismatch!");
                    ipc.Shutdown();
                }
                break;
            case IPCProtocol::EventType::LOG:
                state.logQueue.push_back(event.log.text);
                break;
            case IPCProtocol::EventType::WORKSPACE_READY:
                state.pipeline.activeWorkspace = event.workspaceReady.workspace;
                break;
            case IPCProtocol::EventType::PHASE_STARTED:
                state.pipeline.activePhase = event.phaseStarted.phase;
                state.pipeline.progressLabel = event.phaseStarted.label;
                state.pipeline.runState = RunState::RUNNING;
                break;
            case IPCProtocol::EventType::PROGRESS:
                state.pipeline.phaseProgress = event.progress.value;
                state.pipeline.overallProgress = event.progress.overallValue;
                state.pipeline.progressLabel = event.progress.label;
                break;
            case IPCProtocol::EventType::ACTION_REQUIRED:
                state.pipeline.runState = RunState::AWAITING_ACTION;
                state.pipeline.pendingRequestId = event.actionRequired.requestId;
                state.pipeline.pendingActionType = event.actionRequired.action;
                state.pipeline.pendingPreviewPath = event.actionRequired.preview;
                state.pipeline.pendingCandidateCount = event.actionRequired.count;
                break;
            case IPCProtocol::EventType::DONE:
                state.pipeline.runState = RunState::COMPLETED;
                state.pipeline.latestOutput = event.done.output;
                break;
            case IPCProtocol::EventType::CANCELLED:
                state.pipeline.runState = RunState::CANCELLED;
                break;
            case IPCProtocol::EventType::ERROR:
                state.pipeline.runState = RunState::FAILED;
                state.pipeline.lastErrorCode = event.error.code;
                state.pipeline.lastErrorMessage = event.error.text;
                state.logQueue.push_back("[ERROR] " + event.error.text);
                break;
            default:
                break;
        }
    }
}
