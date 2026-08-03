#pragma once

#include "editor/domain/PipelineTypes.h"
#include "editor/domain/RunState.h"

#include <optional>
#include <vector>

struct EditorState {
    std::vector<RunState> runs;
    std::optional<RunId> selectedRunId;
};
