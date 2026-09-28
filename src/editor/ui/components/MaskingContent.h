#pragma once

#include "editor/ui/UIInput.h"

#include <string>
#include <vector>

struct PhaseDisplayData;

class MaskingContent {
public:
    void Render(
        const PhaseDisplayData& data,
        std::vector<UIInput>& inputs
    );
    void UpdateInteraction(const PhaseDisplayData& data);
    void ResetInteraction();
    void Shutdown();

private:
    bool LoadPreview(const char* path);

    std::string promptRunId_;
    int promptSelectionId_ = -1;
    bool drawingMode_ = false;
    bool dragging_ = false;
    bool hasBox_ = false;
    bool passedDragThreshold_ = false;
    double anchorX_ = 0.0;
    double anchorY_ = 0.0;
    double boxX1_ = 0.0;
    double boxY1_ = 0.0;
    double boxX2_ = 0.0;
    double boxY2_ = 0.0;

    unsigned int textureId_ = 0;
    int textureWidth_ = 0;
    int textureHeight_ = 0;
    std::string loadedPath_;
};
