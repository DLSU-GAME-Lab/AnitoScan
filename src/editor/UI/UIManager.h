#pragma once

#include <iostream>
#include <glad/gl.h>
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
#include "panels/ViewportPanel.h"
#include "panels/InputWindow.h"
#include "panels/MenuToolbar.h"


#include "../IPCClient.h"
#include "../render/Scene.h"
#include "../state/EditorState.h"
#include "../controller/PipelineController.h"

class UIManager {
public:
	static UIManager* GetInstance();
	static bool Initialize(SDL_Window* window, SDL_GLContext glContext, EditorState& state, PipelineController* controller, Scene& scene);

	void BeginNewFrame();
	void DrawAllUIs();
	void EndFrame();
	UIPanel* GetPanelByName(String name);
	UIPanel* GetPanelByType(UIType type);
	void OpenPanel(UIType type);
	void ClosePanel(UIType type);
	void Shutdown();
	void SetWorkspaceForFileViewers(const std::filesystem::path& workspace);
	void ClearWorkspaceFromFileViewers();
	void ApplyLayout(UILayout layout);

	template<typename... Args>
	bool Contains(UIType target, Args... args) {
		return ((args == target) || ...);
	}
	/*void OnlyOpenPanels(Args... args) {

	}*/

private:
    void CreateUIPanels(EditorState& state, PipelineController* controller, Scene& scene);

private:
	UIManager();
	~UIManager();
	UIManager(const UIManager&) = delete;
	UIManager& operator=(const UIManager&) = delete;
	static UIManager* sharedInstance;

private:
	UIList uiList;
	UIMap uiMap;

};
