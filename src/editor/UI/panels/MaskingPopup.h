#pragma once

#include <vector>

#include "../UIPanel.h"
#include "OverviewPanel.h"

class MaskingPopup : public UIPanel {
public:
	MaskingPopup(String name);
	~MaskingPopup();

	void Draw() override;
	void ShowPopup();
	void InitializeEntryFiles();
	void SetImagePreview(int index);

private:
	void LoadPreview(const String& path);
	void ClearPreview();
	void DrawFittedImage(GLuint texture, int imgW, int imgH, ImVec2 availSpace);

private:
	bool showPopup;
	GLuint previewTexture;
	String lastPreviewPath;
	int previewW = 0, previewH = 0;
	int imageIndex = 0;
	std::vector<std::filesystem::path> entryFiles;
};