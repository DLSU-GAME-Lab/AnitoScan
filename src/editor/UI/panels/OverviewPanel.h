#pragma once

#include "../UIPanel.h"
#include "../UIManager.h"
#include "../../IPCClient.h"
#include "../../IPCProtocol.h"

#include <mutex>

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
	void SetPhaseStarted(Phase phase, const String& label);
	void SetPhaseProgress(Phase phase, float value, float overallValue, const String& label);
	void SetPhaseComplete(Phase phase);
	void SetDone();
	void SetCancelled();
	void HandleError(const IPCProtocol::ErrorEvent& err);
	void SetScanning(bool scanning);
	void SetInput(String input, String output, int minFrames, String quality);
	String GetExportQuality();
	Phase GetCurrentPhase();

private:
	void DrawInputSection();
	void DrawActions();
	void DrawOverallProgress();
	void DrawPhaseBreakdown();
	void ResetAllProgress();

private:
	IPCClient& ipc;
	bool isScanning = false;
	bool isCancelling = false;
	bool inputReady = false;
	float overallProgressValue = 0.0f;
	PhaseStatus phases[6]; // Index 1..5 for canonical Phase 1..5
	Phase currentPhase = Phase::NONE;
	String inputFile, outputFolder, quality;
	int minFrames;
	std::mutex uiMutex;
};
