#pragma once

#include <vector>

#include "../UIPanel.h"
#include "OverviewPanel.h"

class MaskingPopup : public UIPanel {
public:
	MaskingPopup(String name, IPCClient& ipc);
	~MaskingPopup();

	void Draw() override;
	void ShowPopup();
	void ShowCandidates(String previewPath, String frame, int count);

private:
	void LoadPreview(const String& path);
	void ClearPreview();
	void DisplayPreview();
	void DisplayCandidatesButton();
	void DisplaySkipButton();

private:
	IPCClient& ipc;
	bool showPopup, isWaiting;
	GLuint previewTexture;
	String lastPreviewPath;
	int previewW = 0, previewH = 0;
	String previewPath, frame;
	int count;

//zoom
private:
	float  zoom = 1.0f;
	ImVec2 panOffset = ImVec2(0, 0);
	bool   isPanning = false;
	ImVec2 lastMouse = ImVec2(0, 0);
};