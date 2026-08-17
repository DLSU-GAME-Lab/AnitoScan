#pragma once

#include "editor/ui/UIInput.h"

#include <string>
#include <vector>

class MaskingContent {
public:
    void Render(
        const std::string& previewPath,
        int candidateCount,
        std::vector<UIInput>& inputs
    );
    void Shutdown();

private:
    bool LoadPreview(const char* path);

    unsigned int textureId_ = 0;
    int textureWidth_ = 0;
    int textureHeight_ = 0;
    std::string loadedPath_;
};
