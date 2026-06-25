#pragma once

#include "../UIPanel.h"
#include "../../render/Scene.h"

class ViewportPanel : public UIPanel {
public:
	ViewportPanel(String name, Scene& scene);
	~ViewportPanel();

	void Draw() override;

	bool IsHovered();

private:
	Scene& scene;
	bool hoveredLastFrame = false;
};