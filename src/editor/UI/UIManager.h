#pragma once

#include <iostream>
#include <SDL.h>
#include <SDL_opengl.h>
#include <backends/imgui_impl_sdl2.h>
#include <backends/imgui_impl_opengl3.h>

#include "../Types.h"
#include "UIPanel.h"
#include "panels/ScanPanel.h"

class UIManager {
public:
	static UIManager* GetInstance();
	static bool Initialize(SDL_Window* window, SDL_GLContext glContext);

	void BeginNewFrame();
	void DrawAllUIs();
	void EndFrame();
	UIPanel* GetPanelByType(UIType type);
	void Shutdown();

private:
	void InitializeUIPanels();

private:
	UIManager();
	~UIManager();
	UIManager(UIManager const&) {};
	UIManager& operator=(UIManager const&) {};
	static UIManager* sharedInstance;

private:
	UIList UIList;
	UIMap UIMap;

};