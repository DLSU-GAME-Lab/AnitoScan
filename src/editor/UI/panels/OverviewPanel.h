#pragma once

#include "../UIPanel.h"
#include "../UIManager.h"
#include "../../IPCClient.h"

enum class InputState {
	Browsing,
	Confirming,
	NamingFolder,
	Ready
};

class OverviewPanel : public UIPanel {
public:
	OverviewPanel(String name, IPCClient& ipc);
	~OverviewPanel();

	void Draw() override;
	//void PushLog(const String& line);
	void SetProgress(float value, const String& label);
	void SetDone();
	std::filesystem::path GetOutputFolder();

private:
	void DrawInputSection();
	void DrawActions();
	void DrawProgress();
	//void DrawLog();

private:
	IPCClient& ipc;
	//std::vector<String> logLines;
//	char inputPath[512] = "";
	bool isScanning;
	bool scrollToBottom;
	float progress;
	String progressLabel;

	ImGui::FileBrowser fileDialog;

	std::filesystem::path fileName;
	std::filesystem::path tempPath;
	std::filesystem::path folderName;
	InputState inputState = InputState::Browsing;
	char inputText[256] = "";
	//bool showInputSection = true;
	//bool hasSelected = false;
	//bool hasInput = false;
};