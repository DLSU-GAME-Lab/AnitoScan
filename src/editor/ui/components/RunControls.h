#pragma once

struct RunState;
class PipelineController;

class RunControls {
public:
    void Render(const RunState& run, bool backendReady, PipelineController& controller);
};
