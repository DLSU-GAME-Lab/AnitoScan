#include "OverviewPanel.h"

#include <chrono>
#include <thread>

#include <nlohmann/json.hpp>

OverviewPanel::OverviewPanel(String name, IPCClient& ipc)
	: UIPanel(UIType::OVERVIEW, name), ipc(ipc) {}

OverviewPanel::~OverviewPanel() {}

// Sets the progress value of a phase
void OverviewPanel::SetPhaseProgress(Phase phase, float value, const String& label) {
	int i = (int)phase;
	if (i < 0 || i >= (int)Phase::COUNT) return;
	this->phases[i].progress = value;
	this->phases[i].label = label;
	this->phases[i].active = true;
	this->currentPhase = phase;

	//std::cout << "Output: " << this->phases[i].progress << std::endl;
}

// Sets a phase to complete
void OverviewPanel::SetPhaseComplete(Phase phase) {
	int i = (int)phase;
	if (i < 0 || i >= (int)Phase::COUNT) return;
	this->phases[i].progress = 1.f;
	this->phases[i].active = false;
	this->phases[i].completed = true;
	this->phases[i].label = "Complete";
}

// Sets the overall progress to complete
void OverviewPanel::SetDone() {
	for (auto& p : phases) {
		p.progress = 1.0f;
		p.completed = true;
		p.active = false;
		p.label = "Complete";
	}
	isScanning = false;
}

void OverviewPanel::SetScanning(bool scanning) {
	this->isScanning = scanning;
}

// Sets the necessary input values to be passed to the backend
void OverviewPanel::SetInput(String input, String output, int minFrames, String quality) {
	this->inputFile = input;
	this->outputFolder = output;
	this->minFrames = minFrames;
	this->quality = quality;
	inputReady = true;
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
	//HighlightImGuiText(this->inputFile, UIColor::GREEN);

	ImGui::Text("Output folder: ");
	ImGui::SameLine();
	HighlightImGuiText(this->outputFolder, UIColor::GREEN);

	ImGui::Text("Minimum Frames: ");
	ImGui::SameLine();
	HighlightImGuiText(std::to_string(this->minFrames), UIColor::GREEN);

	ImGui::Text("Quality");
	ImGui::SameLine();
	HighlightImGuiText(this->quality, UIColor::GREEN);
	ImGui::Spacing();
}


// upper section of the overview panel
void OverviewPanel::DrawActions() {

	// RUN PIPELINE
	ImGui::BeginDisabled(this->isScanning || this->isCleaningUp || !this->inputReady);
	if (ImGui::Button("Run Pipeline")) {
		ResetAllProgress();
		this->isScanning = true;
		//inputReady = false;

		nlohmann::json cmd;
		cmd["action"] = "run_pipeline";
		cmd["name"] = this->outputFolder;
		cmd["input"] = this->inputFile;
		cmd["minimum_frames"] = this->minFrames; 
		cmd["quality"] = this->quality;
		cmd["ipc"] = true;

		//	cmd["fps"] = 10;
		this->ipc.Send(cmd.dump());

		std::cout << "[DEBUG]: Output folder: " << this->outputFolder << std::endl;
		std::cout << "[DEBUG]: Input file: " << this->inputFile << std::endl;

	}
	ImGui::EndDisabled();
	ImGui::SameLine();


	// CANCEL
	ImGui::BeginDisabled(!this->isScanning);
	if (ImGui::Button("Cancel Scan")) {
		ResetAllProgress();
		this->ipc.Shutdown();
		UIManager::GetInstance()->ClearOutputFromFileViewers();
		this->isScanning = false;
		this->isCleaningUp = true;
;
		String runPath = String(PROJECT_ROOT_DIR) + "/data/runs/" + this->outputFolder;
		std::thread([this, runPath]() {
			bool ok = DeleteRunFolder(runPath, 5);
			{
				std::lock_guard<std::mutex> lock(this->uiMutex);
				if(!ok) std::cout << "Failed to clean up folder: " + runPath << std::endl;
				this->isCleaningUp = false;
			}
		}).detach();

		if (!this->ipc.Restart()) {
			std::cerr << "[ERROR]: Failed to restart the configured backend." << std::endl;
		}
	}
	ImGui::EndDisabled();


	ImGui::Spacing();
}

// Displays the overall progress bar
void OverviewPanel::DrawOverallProgress() {
	float overall = CalculateOverallProgress();
	ImGui::SeparatorText("Overall Progress");
	ImGui::ProgressBar(overall, ImVec2(-1, 20));
}


// Displays and updates the progress bars for each phase
void OverviewPanel::DrawPhaseBreakdown() {
	const char* phaseNames[]{
		"Phase 1: Capture",
		"Phase 2: Masking",
		"Phase 3: Spatial",
		"Phase 4: Geometry",
		"Phase 5: Export"
	};

	for (int i = 0; i < (int)Phase::COUNT; i++) {
		auto& p = this->phases[i];
		ImGui::PushID(i);

		UIColor barColor = UIColor::NONE;
		if (p.completed) {
			HighlightImGuiText(String("[DONE] ") + phaseNames[i], UIColor::GREEN);
			barColor = UIColor::GREEN;
		}
		else if (p.active) {
			HighlightImGuiText(String("[ >> ]") + phaseNames[i], UIColor::YELLOW);
			barColor = UIColor::YELLOW;
		}
		else {
			if (!p.label.empty())
				ImGui::TextDisabled("[    ] %s", phaseNames[i]);
		}

		UpdateImGuiProgressBar(p.progress, ImVec2(-1, 12), barColor);	

		if(p.active || p.completed) {
			ImGui::TextDisabled("  %s", p.label.c_str());
		}

		ImGui::Spacing();
		ImGui::PopID();
	}
}

// Compute for the overall progress based on the progress of each phase
float OverviewPanel::CalculateOverallProgress() {
	float total = 0.0f;
	int partial = (int)Phase::COUNT;
	for (int i = 0; i < partial; i++) {
		total += phases[i].progress / partial;
	}
	return total;
}

void OverviewPanel::ResetAllProgress() {
	for (int i = 0; i < (int)Phase::COUNT; i++) {
		this->phases[i].progress = 0.f;
		this->phases[i].active = false;
		this->phases[i].completed = false;
		this->phases[i].label = "Waiting...";
	}
}

bool OverviewPanel::DeleteRunFolder(String path, int maxAttempts) {
	for (int i = 0; i < maxAttempts; i++) {
		try {
			std::error_code ec;
			if(i == 0) std::this_thread::sleep_for(std::chrono::milliseconds(300));

			UIManager::GetInstance()->ClearOutputFromFileViewers();
			std::filesystem::remove_all(path, ec);
			if (!ec) {
				return true;
			}
			std::cout << "Remove_all failed: " << ec.message() << std::endl;
		}
		catch (std::filesystem::filesystem_error e){
			std::cout << "filesystem_error on attempt " << i << ": " << e.what() << std::endl;
		} 
		std::this_thread::sleep_for(std::chrono::milliseconds(300));
	}
	return false;
}


// MAIN DRAW
void OverviewPanel::Draw() {
	ImGui::Begin(this->name.c_str());

	DrawActions();
	ImGui::Separator();
	DrawInputSection();
	
	if(isScanning) {
		DrawOverallProgress();
		DrawPhaseBreakdown();
	}

	ImGui::End();
}