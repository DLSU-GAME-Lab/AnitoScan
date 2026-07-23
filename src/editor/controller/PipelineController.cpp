#include "PipelineController.h"
#include "../IPCProtocol.h"
#include <iostream>

PipelineController::PipelineController(EditorState& state, IPCClient& ipc)
    : state(state), ipc(ipc) {}

void PipelineController::StartBackend(const std::string& executable, const std::vector<std::string>& arguments) {
    if (state.pipeline.backendState != BackendState::STOPPED && state.pipeline.backendState != BackendState::FAILED) return;

    state.pipeline.backendState = BackendState::STARTING;
    if (!ipc.Start(executable, arguments)) {
        state.pipeline.backendState = BackendState::FAILED;
        state.logQueue.push_back("[CRITICAL] Failed to launch backend process.");
    }
}

void PipelineController::StopBackend() {
    state.pipeline.backendState = BackendState::STOPPING;
    ipc.Shutdown();
    state.pipeline.backendState = BackendState::STOPPED;
}

void PipelineController::RestartBackend() {
    StopBackend();
    if (ipc.Restart()) {
        state.pipeline.backendState = BackendState::STARTING;
    } else {
        state.pipeline.backendState = BackendState::FAILED;
    }
}

void PipelineController::StartRun(const std::string& runName, const std::string& input, int minFrames, const std::string& quality) {
    if (state.pipeline.backendState != BackendState::READY || state.pipeline.runState != RunState::IDLE) return;

    state.pipeline.runState = RunState::STARTING;
    state.pipeline.runName = runName;
    state.pipeline.activePhase = Phase::NONE;
    state.pipeline.phaseProgress = 0.0f;
    state.pipeline.overallProgress = 0.0f;
    state.pipeline.latestOutput.clear();
    state.pipeline.ClearPendingAction();

    ipc.Send(IPCProtocol::SerializeRunPipeline(runName, input, minFrames, quality));
}

void PipelineController::CancelRun() {
    if (state.pipeline.runState == RunState::IDLE || state.pipeline.runState == RunState::CANCELLING) return;

    state.pipeline.runState = RunState::CANCELLING; // Graceful wait for 'cancelled' event
    ipc.Send(IPCProtocol::SerializeCancelPipeline(state.pipeline.runName));
}

void PipelineController::SubmitSelection(const std::string& requestId, int choice) {
    if (state.pipeline.actionStatus != SubmissionStatus::PENDING) return;

    state.pipeline.actionStatus = SubmissionStatus::SUBMITTED;
    ipc.Send(IPCProtocol::SerializeSelection(requestId, choice));
}

void PipelineController::SkipSelection(const std::string& requestId) {
    if (state.pipeline.actionStatus != SubmissionStatus::PENDING) return;

    state.pipeline.actionStatus = SubmissionStatus::SUBMITTED;
    ipc.Send(IPCProtocol::SerializeSelectionSkip(requestId));
}

void PipelineController::Tick() {
    std::vector<BackendMessage> messages;
    ipc.Poll(messages);

    // Transport/Process failure detection
    if (state.pipeline.backendState == BackendState::READY || state.pipeline.backendState == BackendState::STARTING) {
        if (!ipc.IsRunning()) {
            state.pipeline.backendState = BackendState::FAILED;
            if (state.pipeline.runState != RunState::IDLE && state.pipeline.runState != RunState::COMPLETED) {
                state.pipeline.runState = RunState::FAILED;
                state.pipeline.ClearPendingAction();
            }
            state.logQueue.push_back("[CRITICAL] Backend process terminated unexpectedly.");
        }
    }

    for (const auto& msg : messages) {
        IPCProtocol::DecodedEvent event = IPCProtocol::DecodeEvent(msg.raw);

        switch (event.type) {
            case IPCProtocol::EventType::BACKEND_READY:
                if (event.backendReady.protocolVersion == IPCProtocol::PROTOCOL_VERSION) {
                    state.pipeline.backendState = BackendState::READY;
                } else {
                    state.logQueue.push_back("[ERROR] Backend protocol version mismatch!");
                    StopBackend();
                    state.pipeline.backendState = BackendState::FAILED;
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
                state.pipeline.phaseProgress = 0.0f;
                state.pipeline.runState = RunState::RUNNING;
                state.pipeline.ClearPendingAction();
                break;

            case IPCProtocol::EventType::PROGRESS:
                state.pipeline.phaseProgress = event.progress.value;
                state.pipeline.overallProgress = event.progress.overallValue;
                state.pipeline.progressLabel = event.progress.label;
                if (state.pipeline.runState == RunState::AWAITING_ACTION && state.pipeline.actionStatus == SubmissionStatus::SUBMITTED) {
                    state.pipeline.runState = RunState::RUNNING;
                    state.pipeline.ClearPendingAction();
                }
                break;

            case IPCProtocol::EventType::ACTION_REQUIRED:
                state.pipeline.runState = RunState::AWAITING_ACTION;
                state.pipeline.pendingRequestId = event.actionRequired.requestId;
                state.pipeline.pendingActionType = event.actionRequired.action;
                state.pipeline.pendingPreviewPath = event.actionRequired.preview;
                state.pipeline.pendingCandidateCount = event.actionRequired.count;
                state.pipeline.actionStatus = SubmissionStatus::PENDING;
                break;

            case IPCProtocol::EventType::PHASE_COMPLETED:
                state.pipeline.runState = RunState::RUNNING;
                state.pipeline.ClearPendingAction();
                break;

            case IPCProtocol::EventType::DONE:
                state.pipeline.runState = RunState::COMPLETED;
                state.pipeline.latestOutput = event.done.output;
                state.pipeline.ClearPendingAction();

                // Publish typed cross-subsystem event for App to dispatch
                state.outputEventAvailable = true;
                state.outputEventPath = event.done.output;
                break;

            case IPCProtocol::EventType::CANCELLED:
                state.pipeline.runState = RunState::CANCELLED;
                state.pipeline.ClearPendingAction();
                break;

            case IPCProtocol::EventType::ERROR:
                state.pipeline.lastErrorCode = event.error.code;
                state.pipeline.lastErrorMessage = event.error.text;
                state.logQueue.push_back("[ERROR] " + event.error.text);

                if (event.error.scope == "command") {
                    // Command-scoped: Reject command, preserve run
                    if (state.pipeline.actionStatus == SubmissionStatus::SUBMITTED) {
                        state.pipeline.actionStatus = SubmissionStatus::PENDING; // Allow retry
                    }
                    if (state.pipeline.runState == RunState::STARTING) {
                        state.pipeline.runState = RunState::IDLE;
                    }
                }
                else if (event.error.scope == "run") {
                    // Run-scoped: Terminate run, preserve backend
                    state.pipeline.runState = RunState::FAILED;
                    state.pipeline.ClearPendingAction();
                }
                else if (event.error.scope == "backend") {
                    // Backend-scoped: Terminate run and backend
                    state.pipeline.runState = RunState::FAILED;
                    state.pipeline.backendState = BackendState::FAILED;
                    state.pipeline.ClearPendingAction();
                }
                break;

            default:
                break;
        }
    }
}
