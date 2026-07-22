#pragma once

#include "../UIPanel.h"
#include "DockSpace.h"

class MenuToolbar : public UIPanel {
public:
	MenuToolbar(String name);
	~MenuToolbar();

	void Draw();
	void SetDockspace(Dockspace* dockspace);

private:
	 Dockspace* dockspace;
};