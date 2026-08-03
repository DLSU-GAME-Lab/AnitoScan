#pragma once

#include <string>

struct RunState;
class PipelineController;

class MaskingContent {
public:
    void Render(const RunState& run, PipelineController& controller);
    void Shutdown();

private:
    bool LoadPreview(const char* path);

    unsigned int textureId_ = 0;
    int textureWidth_ = 0;
    int textureHeight_ = 0;
    std::string loadedPath_;
};
