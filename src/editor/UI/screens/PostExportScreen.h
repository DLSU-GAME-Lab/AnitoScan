#pragma once

#include "editor/ui/components/Viewport.h"

class PostExportScreen {
public:
    void Render(unsigned int textureId);

    int GetViewportWidth() const;
    int GetViewportHeight() const;

private:
    Viewport viewport_;
};
