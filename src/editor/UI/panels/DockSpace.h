#pragma once

#include "imgui.h"
#include "imgui_internal.h"
#include "../UIPanel.h"

class DockSpace : public UIPanel {
public:
	DockSpace();
	~DockSpace();
	void Draw() override;

private:
	void SetupDefaultLayout(ImGuiID dockspaceID);
};