#include "OverviewPanel.h"

OverviewPanel::OverviewPanel(String name, IPCClient& ipc)
	: UIPanel(UIType::OVERVIEW, name), ipc(ipc) {
	ResetAllProgress();
}

OverviewPanel::~OverviewPanel() {}

void OverviewPanel::SetPhaseStarted(Phase phase, const String& label) {
	int i = static_cast<int>(phase);
	if (i < 1 || i >= static_cast<int>(Phase::COUNT)) return;
	this->phases[i].active = true;
	this->phases[i].completed = false;
	this->phases[i].label = label.empty() ? "In Progress" : label;
	this->currentPhase = phase;
}

void OverviewPanel::SetPhaseProgress(Phase phase, float value, float overallValue, const String& label) {
	int i = static_cast<int>(phase);
	if (i >= 1 && i < static_cast<int>(Phase::COUNT)) {
		this->phases[i].progress = value;
		if (!label.empty()) this->phases[i].label = label;
		this->phases[i].active = true;
		this->currentPhase = phase;
	}
	this->overallProgressValue = overallValue;
}

void OverviewPanel::SetPhaseComplete(Phase phase) {
	int i = static_cast<int>(phase);
	if (i < 1 || i >= static_cast<int>(Phase::COUNT)) return;
	this->phases[i].progress = 1.0f;
	this->phases[i].active = false;
	this->phases[i].completed = true;
	this->phases[i].label = "Complete";
}

void OverviewPanel::SetDone() {
	for (int i = 1; i < static_cast<int>(Phase::COUNT); i++) {
		this->phases[i].progress = 1.0f;
		this->phases[i].completed = true;
		this->phases[i].active = false;
		this->phases[i].label = "Complete";
	}
	this->overallProgressValue = 1.0f;
	this->isScanning = false;
	this->isCancelling = false;
}

void OverviewPanel::SetCancelled() {
	this->isScanning = false;
	this->isCancelling = false;
}

void OverviewPanel::HandleError(const IPCProtocol::ErrorEvent& err) {
	if (err.scope == "run" || err.scope == "backend") {
		this->isScanning = false;
		this->isCancelling = false;
	}
}

void OverviewPanel::SetScanning(bool scanning) {
	this->isScanning = scanning;
}

void OverviewPanel::SetInput(String input, String output, int minFrames, String quality) {
	this->inputFile = input;
	this->outputFolder = output;
	this->minFrames = minFrames;
	this->quality = quality;
	this->inputReady = true;
}

String OverviewPanel::GetExportQuality() {
	return this->quality;
}

Phase OverviewPanel::GetCurrentPhase() {
	return this->currentPhase;
}

void OverviewPanel::DrawInputSection() {
	InputWindow* input = static_cast<InputWindow*>(UIManager::GetInstance()->GetPanelByType(UIType::INPUT));

	if (!this->isScanning && !this->inputReady) {
		if (ImGui::Button("Open Input Window"))
			input->ShowWindow();
		return;
	}

	if (this->isScanning) {
		ImGui::SeparatorText("Current Input");
	}
	else {
		if (ImGui::Button("Modify Input"))
			input->ShowWindow();
	}

	ImGui::Spacing();
	ImGui::Text("Selected: ");
	ImGui::SameLine();
	std::filesystem::path path(this->inputFile);
	HighlightImGuiText(path.filename().string(), UIColor::GREEN);

	ImGui::Text("Output folder: ");
	ImGui::SameLine();
	HighlightImGuiText(this->outputFolder, UIColor::GREEN);

	ImGui::Text("Minimum Frames: ");
	ImGui::SameLine();
	HighlightImGuiText(std::to_string(this->minFrames), UIColor::GREEN);

	ImGui::Text("Quality: ");
	ImGui::SameLine();
	HighlightImGuiText(this->quality, UIColor::GREEN);
	ImGui::Spacing();
}

void OverviewPanel::DrawActions() {
	// Disable if backend is not ready, scanning, or cancelling
	ImGui::BeginDisabled(!this->ipc.IsBackendReady() || this->isScanning || this->isCancelling || !this->inputReady);
	if (ImGui::Button("Run Pipeline")) {
		ResetAllProgress();
		this->isScanning = true;

		std::string cmd = IPCProtocol::SerializeRunPipeline(
			this->outputFolder,
			this->inputFile,
			this->minFrames,
			this->quality
		);
		this->ipc.Send(cmd);
	}
	ImGui::EndDisabled();
	ImGui::SameLine();

	// CANCEL
	ImGui::BeginDisabled(!this->isScanning || this->isCancelling);
	if (ImGui::Button("Cancel Scan")) {
		this->isCancelling = true;
		std::string cmd = IPCProtocol::SerializeCancelPipeline(this->outputFolder);
		this->ipc.Send(cmd);
	}
	ImGui::EndDisabled();

	ImGui::Spacing();
}

void OverviewPanel::DrawOverallProgress() {
	ImGui::SeparatorText("Overall Progress");
	ImGui::ProgressBar(this->overallProgressValue, ImVec2(-1, 20));
}

void OverviewPanel::DrawPhaseBreakdown() {
	const char* phaseNames[]{
		"",
		"Phase 1: Capture",
		"Phase 2: Masking",
		"Phase 3: Spatial",
		"Phase 4: Geometry",
		"Phase 5: Export"
	};

	for (int i = 1; i < static_cast<int>(Phase::COUNT); i++) {
		auto& p = this->phases[i];
		ImGui::PushID(i);

		UIColor barColor = UIColor::NONE;
		if (p.completed) {
			HighlightImGuiText(String("[DONE] ") + phaseNames[i], UIColor::GREEN);
			barColor = UIColor::GREEN;
		}
		else if (p.active) {
			HighlightImGuiText(String("[ >> ] ") + phaseNames[i], UIColor::YELLOW);
			barColor = UIColor::YELLOW;
		}
		else {
			ImGui::TextDisabled("[    ] %s", phaseNames[i]);
		}

		UpdateImGuiProgressBar(p.progress, ImVec2(-1, 12), barColor);

		if (p.active || p.completed) {
			ImGui::TextDisabled("  %s", p.label.c_str());
		}

		ImGui::Spacing();
		ImGui::PopID();
	}
}

void OverviewPanel::ResetAllProgress() {
	this->overallProgressValue = 0.0f;
	for (int i = 1; i < static_cast<int>(Phase::COUNT); i++) {
		this->phases[i].progress = 0.0f;
		this->phases[i].active = false;
		this->phases[i].completed = false;
		this->phases[i].label = "Waiting...";
	}
}

void OverviewPanel::Draw() {
	ImGui::Begin(this->name.c_str());

	DrawActions();
	ImGui::Separator();
	DrawInputSection();

	if (this->isScanning || this->isCancelling) {
		DrawOverallProgress();
		DrawPhaseBreakdown();
	}

	ImGui::End();
}
