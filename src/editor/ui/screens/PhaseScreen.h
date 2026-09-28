#pragma once

#include "editor/ui/components/ExportContent.h"
#include "editor/ui/components/LogView.h"
#include "editor/ui/components/MaskingContent.h"
#include "editor/ui/components/RunControls.h"

#include <vector>

struct PhaseDisplayData;
struct UIInput;

class PhaseScreen {
public:
    void Render(const PhaseDisplayData& data, std::vector<UIInput>& inputs);
    void ResetInteraction();
    void Shutdown();

private:
    LogView logView_;
    RunControls runControls_;
    MaskingContent maskingContent_;
    ExportContent exportContent_;
};
