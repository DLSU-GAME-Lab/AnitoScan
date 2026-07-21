#pragma once

#include "../UIPanel.h"

class Dockspace : public UIPanel {
public:
	Dockspace(String name);
	~Dockspace();
	void Draw() override;

	void RequestDefaultLayout();       
	void RequestModelViewerLayout();

private:
	void SetupDefaultLayout();
	void SetupModelViewerLayout();

private:
	ImGuiID dockspaceID = 0;

	enum class PendingLayout { None, Default, ModelViewer };
	PendingLayout pendingLayout = PendingLayout::Default;

};