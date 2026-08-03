#pragma once

struct EditorState;
class PipelineController;

class RunSelector {
public:
    void Render(const EditorState& state, PipelineController& controller);
};
