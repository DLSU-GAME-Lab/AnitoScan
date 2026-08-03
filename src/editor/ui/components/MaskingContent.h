#pragma once

struct RunState;
class PipelineController;

class MaskingContent {
public:
    void Render(const RunState& run, PipelineController& controller);
};
