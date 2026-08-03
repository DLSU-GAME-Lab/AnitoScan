#pragma once

#include "editor/ui/components/LogView.h"
#include "editor/ui/components/MaskingContent.h"
#include "editor/ui/components/RunControls.h"

#include <string>
#include <vector>

struct RunState;
class PipelineController;

class PhaseScreen {
public:
    void Render(
        const RunState& run,
        bool backendReady,
        const std::vector<std::string>& logs,
        PipelineController& controller
    );

private:
    LogView logView_;
    RunControls runControls_;
    MaskingContent maskingContent_;
};
