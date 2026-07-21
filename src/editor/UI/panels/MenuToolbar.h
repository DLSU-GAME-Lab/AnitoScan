#pragma once

#include "../UIPanel.h"
#include "Dockspace.h"

class MenuToolbar : public UIPanel {
public:
	MenuToolbar(String name);
	~MenuToolbar();

	void Draw();
	void SetDockspace(Dockspace* dockspace);

private:
	void SelectModelToImport();

private:
	 Dockspace* dockspace;
	 bool displayImport = true;
	 ImGui::FileBrowser fileDialog;
};