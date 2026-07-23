#pragma once
#include <string>
#include <vector>
#include "../Phase.h"
#include "../IPCProtocol.h"

enum class BackendState {
    STOPPED,
    STARTING,
    READY,
    STOPPING,
    FAILED
};

enum class RunState {
    IDLE,
    STARTING,
    RUNNING,
    AWAITING_ACTION,
    CANCELLING,
    COMPLETED,
    CANCELLED,
    FAILED
};

enum class SubmissionStatus {
    NONE,
    PENDING,
    SUBMITTED
};

struct PipelineState {
    BackendState backendState = BackendState::STOPPED;
    RunState runState = RunState::IDLE;
    Phase activePhase = Phase::NONE;

    std::string runName;
    std::string activeWorkspace;
    std::string latestOutput;

    float phaseProgress = 0.0f;
    float overallProgress = 0.0f;
    std::string progressLabel;

    // Action requirements
    std::string pendingRequestId;
    std::string pendingActionType;
    std::string pendingPreviewPath;
    int pendingCandidateCount = 0;
    SubmissionStatus actionStatus = SubmissionStatus::NONE;

    // Error tracking
    std::string lastErrorCode;
    std::string lastErrorMessage;

    void ClearPendingAction() {
        pendingRequestId.clear();
        pendingActionType.clear();
        pendingPreviewPath.clear();
        pendingCandidateCount = 0;
        actionStatus = SubmissionStatus::NONE;
    }
};
