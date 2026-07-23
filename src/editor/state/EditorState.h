#pragma once
#include "PipelineState.h"
#include <vector>
#include <string>

struct EditorState {
    PipelineState pipeline;

    // UI Notification/Log Queue (Controller writes, UI reads & clears)
    std::vector<std::string> logQueue;

    // Cross-subsystem events (App reads & clears, then dispatches)
    bool outputEventAvailable = false;
    std::string outputEventPath;
};
