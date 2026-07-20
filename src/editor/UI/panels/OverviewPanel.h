#pragma once

#include "../UIPanel.h"
#include "../UIManager.h"
#include "../../IPCClient.h"

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
	void SetInput(String input, String output, int minFrames, String quality);
	String GetExportQuality();
	Phase GetCurrentPhase();

private:
	void DrawInputSection();
	void DrawActions();
	void DrawOverallProgress();
	void DrawPhaseBreakdown();
	float CalculateOverallProgress();
	void ResetAllProgress();
	bool DeleteRunFolder(String path, int maxAttempts);

private:
	IPCClient& ipc;
	bool isScanning = false;
	bool inputReady = false;
	bool isCleaningUp = false;
	PhaseStatus phases[5];
	Phase currentPhase = Phase::NONE;
	String inputFile, outputFolder, quality;
	int minFrames;
	std::mutex uiMutex;
};