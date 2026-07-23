#pragma once

#include <vector>

#include "../UIPanel.h"
#include "OverviewPanel.h"
#include "../../controller/PipelineController.h"

class MaskingPopup : public UIPanel {
public:
    MaskingPopup(String name, const EditorState& state, PipelineController* controller);
	~MaskingPopup();

	void Draw() override;
	void ShowPopup();
	void ShowCandidates(String requestId, String previewPath, String frame, int count);

private:
	void LoadPreview(const String& path);
	void ClearPreview();
	void DisplayPreview();
	void DisplayCandidatesButton();
	void DisplaySkipButton();

private:
    const EditorState& state;
	PipelineController* controller;
	bool showPopup;
	GLuint previewTexture;
	String lastPreviewPath;
	int previewW = 0, previewH = 0;
	String requestId;
	String previewPath, frame;
	int count = 0;

// zoom & pan
private:
	float  zoom = 1.0f;
	ImVec2 panOffset = ImVec2(0, 0);
	ImVec2 lastMouse = ImVec2(0, 0);
};
