#pragma once

#include "editor/ui/components/Viewport.h"

class PipelineController;

class PostExportScreen {
public:
    void Render(unsigned int textureId, PipelineController& controller);

    int GetViewportWidth() const;
    int GetViewportHeight() const;
    bool IsViewportHovered() const;
    bool ConsumeRecenterRequest();

private:
    Viewport viewport_;
    bool recenterRequested_ = false;
};
