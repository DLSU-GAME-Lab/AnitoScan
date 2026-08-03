#pragma once

#include "editor/domain/PipelineTypes.h"

#include <string>

struct EditorState;
class PipelineController;

class RunSelector {
public:
    void Render(const EditorState& state, PipelineController& controller);

private:
    RunId pendingDeleteRunId_;
    std::string pendingDeleteRunName_;
};
