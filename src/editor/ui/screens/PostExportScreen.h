#pragma once

#include "editor/ui/components/Viewport.h"

class PipelineController;

class PostExportScreen {
public:
    void Render(unsigned int textureId, PipelineController& controller);

    int GetViewportWidth() const;
    int GetViewportHeight() const;

private:
    Viewport viewport_;
};
