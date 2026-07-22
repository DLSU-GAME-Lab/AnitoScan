#pragma once

#include "../UIPanel.h"
#include "../../render/Scene.h"
#include "OverviewPanel.h"

class ViewportPanel : public UIPanel {
public:
	ViewportPanel(String name, Scene& scene);
	~ViewportPanel();

	void Draw() override;
	void LoadOutputModel(const String& modelPath);

	bool IsHovered();

private:
	Scene& scene;
	bool hoveredLastFrame = false;
};
