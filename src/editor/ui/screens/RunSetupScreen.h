#pragma once

#include "editor/domain/PipelineTypes.h"
#include "editor/ui/components/RunSelector.h"

#include <array>
#include <string>

struct EditorState;
class PipelineController;

class RunSetupScreen {
public:
    void Render(const EditorState& state, PipelineController& controller);

private:
    std::array<char, 128> runName_{};
    std::array<char, 256> inputSource_{};
    RunConfig config_;
    RunSelector runSelector_;
    std::string creationError_;
};
