#pragma once

#include "../UIPanel.h"
#include "../../IPCClient.h"

class ScanPanel : public UIPanel {
public:
	ScanPanel(IPCClient& ipc);
	~ScanPanel();

	void Draw() override;
	void PushLog(const String& line);
	void SetProgress(float value, String& label);
	void SetDone();

private:
	void DrawActions();
	void DrawProgress();
	void DrawLog();

private:
	IPCClient& ipc;
	std::vector<String> logLines;
	char inputPath[512] = "";
	bool isScanning;
	bool scrollToBottom;
	float progress;
	String progressLabel;
};