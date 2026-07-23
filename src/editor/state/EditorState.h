#pragma once
#include "PipelineState.h"

struct EditorState {
    PipelineState pipeline;

    // UI Notification/Log Queue (Controller writes, UI reads & clears)
    std::vector<std::string> logQueue;
};
