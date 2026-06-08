#pragma once

#include <iostream>
#include <SDL.h>
#include <SDL_opengl.h>
#include <backends/imgui_impl_sdl2.h>
#include <backends/imgui_impl_opengl3.h>

#include "../Types.h"
#include "UIPanel.h"
#include "panels/OverviewPanel.h"
#include "panels/DockSpace.h"
#include "panels/FileViewer.h"
#include "panels/LogPanel.h"
#include "panels/MaskingPopup.h"

#include "../IPCClient.h"

class UIManager {
public:
	static UIManager* GetInstance();
	static bool Initialize(SDL_Window* window, SDL_GLContext glContext, IPCClient& ipc);

	void BeginNewFrame();
	void DrawAllUIs();
	void EndFrame();
	UIPanel* GetPanelByName(String name);
	UIPanel* GetPanelByType(UIType type);
	void Shutdown();
	void SetOutputToFileViewers(std::filesystem::path output);

private:
	void CreateUIPanels(IPCClient& ipc);

private:
	UIManager();
	~UIManager();
	UIManager(UIManager const&) {};
	UIManager& operator=(UIManager const&) {};
	static UIManager* sharedInstance;

private:
	UIList uiList;
	UIMap uiMap;

};