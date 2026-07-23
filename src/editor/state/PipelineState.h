#pragma once
#include <string>
#include <vector>
#include "../Phase.h"
#include "../IPCProtocol.h"

enum class RunState {
    IDLE,
    STARTING,
    RUNNING,
    AWAITING_ACTION,
    COMPLETED,
    CANCELLED,
    FAILED
};

struct PipelineState {
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

    // Error tracking
    std::string lastErrorCode;
    std::string lastErrorMessage;
};
