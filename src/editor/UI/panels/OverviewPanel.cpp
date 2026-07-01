#include "OverviewPanel.h"

OverviewPanel::OverviewPanel(String name, IPCClient& ipc)
	: UIPanel(UIType::OVERVIEW, name), ipc(ipc) {}

OverviewPanel::~OverviewPanel() {}

void OverviewPanel::SetPhaseProgress(Phase phase, float value, const String& label) {
	int i = (int)phase;
	if (i < 0 || i >= (int)Phase::COUNT) return;
	this->phases[i].progress = value;
	this->phases[i].label = label;
	this->phases[i].active = true;
	this->currentPhase = phase;

	//std::cout << "Output: " << this->phases[i].progress << std::endl;
}

void OverviewPanel::SetPhaseComplete(Phase phase) {
	int i = (int)phase;
	if (i < 0 || i >= (int)Phase::COUNT) return;
	this->phases[i].progress = 1.f;
	this->phases[i].active = false;
	this->phases[i].completed = true;
	this->phases[i].label = "Complete";
}

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

	if (!inputReady) {
		if (ImGui::Button("Open input window")) {	
			input->ShowWindow();
		}
	}
	else {
		if (ImGui::Button("Modify Input")) {
			input->ShowWindow();
		}
		ImGui::Spacing();

		ImGui::Text("Selected: ");
		ImGui::SameLine();
		HighlightImGuiText(this->inputFile, UIColor::GREEN);

		ImGui::Text("Output folder: ");
		ImGui::SameLine();
		HighlightImGuiText(this->outputFolder, UIColor::GREEN);

		ImGui::Text("Minimum Frames: ");
		ImGui::SameLine();
		HighlightImGuiText(std::to_string(this->minFrames), UIColor::GREEN);

		ImGui::Text("Quality");
		ImGui::SameLine();
		HighlightImGuiText(this->quality, UIColor::GREEN);

	}
}



// upper section of the overview panel
void OverviewPanel::DrawActions() {
	ImGui::BeginDisabled(!this->isScanning && !inputReady);
	if (ImGui::Button("Run Pipeline")) {
		this->isScanning = true;

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

	ImGui::BeginDisabled(!this->isScanning);


	//TODO: implement cancellation option on every phase once pipeline.py is connected
	// cancel button is not working properly atm
	if (ImGui::Button("Cancel")) {
		this->isScanning = false;
		this->ipc.Shutdown();
		//this->inputReady = false;	
		//this->ipc.Start(".venv\\Scripts\\python.exe", "src/pipeline/core/pipeline.py --ipc");
		//this->ipc.Start(".venv\\Scripts\\python.exe", "src/pipeline/core/dummy.py");
	}
	ImGui::EndDisabled();
	ImGui::Spacing();
}

// overall progress bar
void OverviewPanel::DrawOverallProgress() {
	float overall = CalculateOverallProgress();
	ImGui::SeparatorText("Overall Progress");
	ImGui::ProgressBar(overall, ImVec2(-1, 20));
//	ImGui::Text("%.0f%%", overall * 100.0f);
}


// progress bars for each phase
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
			//barColor = UIColor::
		}

		UpdateImGuiProgressBar(p.progress, ImVec2(-1, 12), barColor);

		if(p.active || p.completed) {
			ImGui::TextDisabled("  %s", p.label.c_str());
		}

		ImGui::Spacing();
		ImGui::PopID();
	}
}

float OverviewPanel::CalculateOverallProgress() {
	float total = 0.0f;
	int partial = (int)Phase::COUNT;
	for (int i = 0; i < partial; i++) {
		total += phases[i].progress / partial;
	}
	return total;
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