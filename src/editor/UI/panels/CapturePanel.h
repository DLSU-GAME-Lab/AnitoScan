#pragma once

//#include <SDL.h>
#include <SDL_opengl.h>
#include "imgui.h"
#include "imfilebrowser.h"
#include "imgui_internal.h"
//#include <backends/imgui_impl_sdl2.h>
//#include <backends/imgui_impl_opengl3.h>

#include "../../Types.h"
#include "../UIPanel.h"

class CapturePanel : public UIPanel {
public:
	CapturePanel();
	~CapturePanel();
	void Draw() override;

private:
	void DrawDefaultBrowser();
	void DrawBrowserTable();
	void LoadPreview(const std::string& path);
	void ClearPreview();
	void DrawFittedImage(GLuint texture, int imgW, int imgH, ImVec2 availSpace);

private:
	ImGui::FileBrowser fileDialog;
	GLuint previewTexture;
	String lastPreviewPath;
	int previewW = 0, previewH = 0;
};	