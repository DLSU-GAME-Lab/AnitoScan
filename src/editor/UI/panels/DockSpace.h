#pragma once

#include "../UIPanel.h"

class DockSpace : public UIPanel {
public:
	DockSpace(String name);
	~DockSpace();
	void Draw() override;

private:
	void SetupDefaultLayout(ImGuiID dockspaceID);
};