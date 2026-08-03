#pragma once

#include "editor/ui/components/RunSelector.h"

#include <array>

struct EditorState;
class PipelineController;

class RunSetupScreen {
public:
    void Render(const EditorState& state, PipelineController& controller);

private:
    std::array<char, 128> runName_{};
    RunSelector runSelector_;
};
