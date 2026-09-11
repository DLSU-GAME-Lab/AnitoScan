#pragma once

#include "editor/ui/components/RunSelector.h"

#include <array>
#include <vector>

struct RunSetupData;
struct UIInput;

class RunSetupScreen {
public:
    void Render(const RunSetupData& data, std::vector<UIInput>& inputs);

private:
    std::array<char, 128> runName_{};
    std::array<char, 256> inputSource_{};
    int minimumFrames_ = 45;
    int pipelineMode_ = 0;
    int captureMode_ = 0;
    int quality_ = 0;
    float iouThreshold_ = 0.5f;
    int driftLimit_ = 200;
    int modelSize_ = 1;
    bool forceRebuild_ = false;
    RunSelector runSelector_;
};
