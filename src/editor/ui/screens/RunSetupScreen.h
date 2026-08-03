#pragma once

#include <array>

class PipelineController;

class RunSetupScreen {
public:
    void Render(PipelineController& controller);

private:
    std::array<char, 128> runName_{};
};
