#pragma once

#include "../UIPanel.h"

class InputPanel : public UIPanel {
public:
	InputPanel(String name);
	~InputPanel();
	
	void Draw() override;

private:
	ImGui::FileBrowser fileDialog;

};