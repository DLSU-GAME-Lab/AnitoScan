#include "OverviewPanel.h"

OverviewPanel::OverviewPanel(String name, IPCClient& ipc) : UIPanel(UIType::OVERVIEW, name), ipc(ipc) {
//	this->isScanning = false;
	this->scrollToBottom = true;	
//	this->progress = 0.0f;
	//this->progressLabel = "Idle";

	//file browser
	this->fileDialog.SetTypeFilters({ ".mp4", ".MOV" });
	this->fileDialog.SetPwd(std::filesystem::current_path() / "data" / "input");
}

OverviewPanel::~OverviewPanel() {}

//void OverviewPanel::SetProgress(float value, const String& label) {
//	this->progress = value;
//	this->progressLabel = label;
//}

void OverviewPanel::SetPhaseProgress(Phase phase, float value, const String& label) {
	int i = (int)phase;
	if (i < 0 || i >= (int)Phase::COUNT) return;
	this->phases[i].progress = value;
	this->phases[i].label = label;
	this->phases[i].active = true;
	this->currentPhase = phase;
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

std::filesystem::path OverviewPanel::GetOutputFolder() {
	return this->folderName;
}

Phase OverviewPanel::GetCurrentPhase() {
	return this->currentPhase;
}

void OverviewPanel::DrawInputSection() {                                         
	if (inputState == InputState::Ready) return;

	ImGui::BeginChild("##Input", ImVec2(0, 0), true);

	if (inputState == InputState::Browsing) {
		ImGui::SeparatorText("Select Input Video");
		if (ImGui::Button("Open File Browser")) {
			this->fileDialog.Open();
		}
	}

	this->fileDialog.Display();

	// INPUT: select video
	if (this->fileDialog.HasSelected() && inputState == InputState::Browsing) {
		tempPath = this->fileDialog.GetSelected();
		inputState = InputState::Confirming;
	//	std::cout << this->inputPath.filename().string() << std::endl;
	}

	if (inputState == InputState::Confirming) {
		ImGui::Text("Selected: "); ImGui::SameLine();
		String file = tempPath.filename().string();
		HighlightImGuiText(file, UIColor::YELLOW);

		//confirmation section
		ImGui::NewLine();
		ImGui::SeparatorText("Proceed with this input?");
		if (ImGui::Button("Yes")) {
			inputState = InputState::NamingFolder;
			this->fileName = file;
		}

		ImGui::SameLine();
		if (ImGui::Button("No")) {
			inputState = InputState::Browsing;
			this->fileDialog.ClearSelected();
			tempPath = "";
		}
	}

	//INPUT: name the folder where the output will be stored
	static std::string input = "";
	if (inputState == InputState::NamingFolder) {
		ImGui::SeparatorText("Enter folder name: ");
		bool confirm = ImGui::InputText("##FolderName", this->inputText, sizeof(this->inputText),
										ImGuiInputTextFlags_EnterReturnsTrue);

		ImGui::SameLine();
		confirm |= ImGui::Button("Enter"); //either Enter key or button click

		if (confirm && this->inputText[0] != '\0') {
			folderName = String(this->inputText);
			inputState = InputState::Ready;
		}
	}
	//std::cout << input.c_str() << std::endl;
	ImGui::EndChild();
}


void OverviewPanel::DrawActions() {
	ImGui::BeginDisabled(!this->isScanning && inputState != InputState::Ready);
	if (ImGui::Button("Run Pipeline")) {
	//	UIManager::GetInstance()->SetRootToFileViewers(this->folderName);
		this->isScanning = true;
	//	this->progress = 0.0f;
	//	this->progressLabel = "Starting...";
		//this->logLines.clear();

		nlohmann::json cmd;
		cmd["action"] = "run_pipeline";
		cmd["name"] = this->folderName;
		cmd["input"] = this->fileName;


		//	cmd["fps"] = 10;
		this->ipc.Send(cmd.dump());

		std::cout << "[DEBUG]: Output folder: " << this->folderName << std::endl;
		std::cout << "[DEBUG]: Input file: " << this->fileName << std::endl;
	}


	ImGui::EndDisabled();

	ImGui::SameLine();

	ImGui::BeginDisabled(!this->isScanning);


	//TODO: implement cancellation option on every phase once pipeline.py is connected
	//if (ImGui::Button("Cancel")) {
	//	this->isScanning = false;
	//	this->ipc.Shutdown();
	//	ipc.Start(".venv\\Scripts\\python.exe", "src/pipeline/core/dummy.py");
	//}

	if (ImGui::Button("Cancel")) {
		this->isScanning = false;
		this->ipc.Shutdown();
		//ipc.Start(".venv\\Scripts\\python.exe", "src/pipeline/core/pipeline.py");
		this->ipc.Start(".venv\\Scripts\\python.exe", "src/pipeline/core/pipeline.py --ipc");
	}
	ImGui::EndDisabled();



	//INPUT
	ImGui::Text("Selected: "); 
	ImGui::SameLine();
	if (inputState == InputState::Browsing || inputState == InputState::Confirming) {
		HighlightImGuiText("No Input yet...", UIColor::RED);
	}
	else {
		HighlightImGuiText(this->fileName.string().c_str(), UIColor::GREEN);
		ImGui::SameLine();
		RightAlignElement("Change##1");
		if (ImGui::Button("Change##1")) {
			inputState = InputState::Browsing;
			this->fileDialog.ClearSelected();
		}
	}

	ImGui::Text("Folder Name: ");
	ImGui::SameLine();
	if (inputState != InputState::Ready) {
		HighlightImGuiText("No Input yet...", UIColor::RED);
	}
	else {
		HighlightImGuiText(this->folderName.string().c_str(), UIColor::GREEN);
		ImGui::SameLine();
		RightAlignElement("Change##2");
		if (ImGui::Button("Change##2")) {
			inputState = InputState::NamingFolder;
			
		}
	}
}


void OverviewPanel::DrawOverallProgress() {
	float overall = CalculateOverallProgress();
	ImGui::SeparatorText("Overall Progress");
	ImGui::ProgressBar(overall, ImVec2(-1, 20));
	ImGui::Text("%.0f%%", overall * 100.0f);
}


void OverviewPanel::DrawPhaseBreakdown() {
	const char* phaseNames[]{
		"Phase 1: Capture",
		"Phase 2: Masking",
		"Phase 3: Spatial",
		"Phase 4: Geometry"
	};

	for (int i = 0; i < (int)Phase::COUNT; i++) {
		auto& p = this->phases[i];

		if (p.completed) {
			HighlightImGuiText(String("[DONE] ") + phaseNames[i], UIColor::GREEN);
		}
		else if (p.active) {
			HighlightImGuiText(String("[ >> ]") + phaseNames[i], UIColor::YELLOW);
		}
		else {
			ImGui::TextDisabled("[    ] %s", phaseNames[i]);
		}

		String barID = "##phase" + std::to_string(i);
		ImGui::ProgressBar(p.progress, ImVec2(-1, 12), barID.c_str());

		if(p.active || p.completed) {
			ImGui::TextDisabled("  %s", p.label.c_str());
		}

		ImGui::Spacing();
	}
}

float OverviewPanel::CalculateOverallProgress() {
	float total = 0.0f;
	int partial = (int)Phase::COUNT;
	for (int i = 0; i < partial; i++) {
		total += phases[i].progress * partial;
	}
	return total;
}




//incomplete
//void OverviewPanel::DrawProgress() {
//	//if (this->isScanning && this->progress > 0.0f) {
//	//	ImGui::ProgressBar(this->progress, ImVec2(-1, 0));
//	//	ImGui::Text("%.0f%% - %s", this->progress * 100.0f, this->progressLabel.c_str());
//	//}
//}

// MAIN DRAW
void OverviewPanel::Draw() {
	ImGui::Begin(this->name.c_str());

	DrawActions();
	ImGui::Separator();

	DrawOverallProgress();
	DrawPhaseBreakdown();
	ImGui::Separator();

	DrawInputSection();

	ImGui::End();
}