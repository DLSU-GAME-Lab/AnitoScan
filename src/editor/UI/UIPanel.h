#pragma once

#include "../Types.h"
#include "imgui.h" 

class UIManager;

class UIPanel {
public:
	UIPanel(UIType type);
	UIPanel(UIType type, bool isActive);
	~UIPanel();

	UIType GetType();
	bool IsActive();
	void SetActive(bool isActive);
	
	virtual void Draw() = 0;

private:
	bool activeSelf;
	UIType type;
};