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


struct PhaseStatus {
	float progress = 0.0f;
	String label = "Waiting...";
	bool completed = false;
	bool active = false;
};

class OverviewPanel : public UIPanel {
public:
	OverviewPanel(String name, IPCClient& ipc);
	~OverviewPanel();

	void Draw() override;
	void SetPhaseProgress(Phase phase, float value, const String& label);
	void SetPhaseComplete(Phase phase);
	void SetDone();
	void SetScanning(bool scanning);
	std::filesystem::path GetOutputFolder();
	std::filesystem::path GetInputFilename();
	Phase GetCurrentPhase();

private:
	void DrawInputSection();
	void DrawActions();
	void DrawOverallProgress();
	void DrawPhaseBreakdown();
	float CalculateOverallProgress();

private:
	IPCClient& ipc;
	bool isScanning = false;
	bool scrollToBottom;
	PhaseStatus phases[5];
	Phase currentPhase = Phase::NONE;

	ImGui::FileBrowser fileDialog;

	std::filesystem::path fileName;
	std::filesystem::path tempPath;
	std::filesystem::path folderName;
	InputState inputState = InputState::Browsing;
	char inputText[256] = "";
};