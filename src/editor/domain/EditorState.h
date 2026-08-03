#pragma once

#include "editor/domain/PipelineTypes.h"
#include "editor/domain/RunState.h"

#include <optional>
#include <string>
#include <vector>

struct EditorState {
    bool backendReady = false;
    std::vector<std::string> logs;
    std::vector<RunState> runs;
    std::optional<RunId> selectedRunId;
};
