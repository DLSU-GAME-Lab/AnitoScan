#pragma once

#include "../Types.h"
#include "imgui.h" 

class UIManager;

class UIPanel {
public:
	UIPanel(UIType type, String name);
	UIPanel(UIType type, String name, bool isActive);
	~UIPanel();

	UIType GetType();
	String GetName();
	bool IsActive();
	void SetActive(bool isActive);
	
	virtual void Draw() = 0;

protected:
	UIType type;
	String name;
	bool activeSelf;
};