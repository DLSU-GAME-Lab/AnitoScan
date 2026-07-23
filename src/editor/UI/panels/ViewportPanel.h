#pragma once
#include "../UIPanel.h"
#include "../../render/Scene.h"
#include "../../state/EditorState.h"

class ViewportPanel : public UIPanel {
public:
    ViewportPanel(String name, Scene& scene, const EditorState& state);
    ~ViewportPanel();

    void Draw() override;
    bool IsHovered();

private:
    Scene& scene;
    const EditorState& state;
    bool hoveredLastFrame = false;
    String loadedModelPath;
};
