#pragma once

#include "editor/ui/components/Viewport.h"

struct EditorState;

class PostExportScreen {
public:
    void Render(const EditorState& state, unsigned int textureId);

    int GetViewportWidth() const;
    int GetViewportHeight() const;

private:
    Viewport viewport_;
};
