#pragma once

//#include "../../Types.h"
#include "../UIPanel.h"
#include "OverviewPanel.h"

class FileViewer : public UIPanel {
public:
	FileViewer(String name, Phase phase);
	~FileViewer();

	void Draw() override;
	void SetOutputFolderToView(std::filesystem::path root);
	void ToggleRefresh(bool isRefreshing);

private:
	void DrawDefaultBrowser();
	void DrawBrowserTable();
	void LoadPreview(const String& path);
	void ClearPreview();
	void DrawFittedImage(GLuint texture, int imgW, int imgH, ImVec2 availSpace);


private:
	ImGui::FileBrowser fileDialog;
	GLuint previewTexture;
	String lastPreviewPath;
	int previewW = 0, previewH = 0;
	bool isRefreshing = true;
	float refreshTimer = 0.0f;
	const float refreshInterval = 0.3f;
	std::filesystem::path output;
	Phase phase;
	bool hasRootFolder = false;
};