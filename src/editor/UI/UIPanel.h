#pragma once

#include <SDL_opengl.h>
#include <imgui.h>
#include <imgui_internal.h>
#include <iostream>
#include <stb_image.h>
#include <imfilebrowser.h>

#include "../Types.h"
#include "UIHelper.h"

class UIManager;

class UIPanel {
public:
	UIPanel(String name);
	//UIPanel(UIType type);
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