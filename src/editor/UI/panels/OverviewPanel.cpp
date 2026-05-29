#include "OverviewPanel.h"

OverviewPanel::OverviewPanel(String name, IPCClient& ipc) : UIPanel(UIType::SCAN_PANEL, name), ipc(ipc) {
	this->isScanning = false;
	this->scrollToBottom = true;	
	this->progress = 0.0f;
	this->progressLabel = "Idle";

	//file browser
	this->fileDialog.SetTypeFilters({ ".mp4", ".MOV" });
	this->fileDialog.SetPwd(std::filesystem::current_path() / "data" / "input");
}

OverviewPanel::~OverviewPanel() {}

void OverviewPanel::SetProgress(float value, String& label) {
	this->progress = value;
	this->progressLabel = label;
}

void OverviewPanel::SetDone() {
	this->isScanning = false;
	this->progress = 1.0f;
	this->progressLabel = "Complete";
}

std::filesystem::path OverviewPanel::GetOutputFolder() {
	return this->folderName;
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
		bool confirm = ImGui::InputText("##FolderName", inputText, sizeof(inputText),
										ImGuiInputTextFlags_EnterReturnsTrue);

		ImGui::SameLine();
		confirm |= ImGui::Button("Enter"); //either Enter key or button click

		if (confirm && inputText[0] != '\0') {
			folderName = String(inputText);
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
		this->progress = 0.0f;
		this->progressLabel = "Starting...";
		//this->logLines.clear();

		nlohmann::json cmd;
		cmd["action"] = "run_pipeline";
		cmd["name"] = this->folderName;
		cmd["input"] = this->fileName;


		//	cmd["fps"] = 10;
		this->ipc.Send(cmd.dump());

		std::cout << "folder: " << this->folderName << std::endl;
		std::cout << "file: " << this->fileName << std::endl;
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


//incomplete
void OverviewPanel::DrawProgress() {
	if (this->isScanning && this->progress > 0.0f) {
		ImGui::ProgressBar(this->progress, ImVec2(-1, 0));
		ImGui::Text("%.0f%% - %s", this->progress * 100.0f, this->progressLabel.c_str());
	}
}

// MAIN DRAW
void OverviewPanel::Draw() {
	ImGui::Begin(this->name.c_str());

	DrawActions();
	ImGui::Separator();
	//DrawProgress();
	//ImGui::Separator();
//	DrawLog();
	//ImGui::Separator();
	DrawInputSection();
	//DrawTest();

	ImGui::End();
}