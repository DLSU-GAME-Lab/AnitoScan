#include "InputPanel.h"

InputPanel::InputPanel(String name) : UIPanel(UIType::INPUT_PANEL, name) {
	this->fileDialog = ImGui::FileBrowser(ImGuiFileBrowserFlags_NoModal);
	this->fileDialog.SetTypeFilters({ ".mp4", ".MOV" });
	this->fileDialog.SetPwd(std::filesystem::current_path() / "data" / "input");
}

InputPanel::~InputPanel() {}

void InputPanel::Draw() {
	ImGui::Begin(this->name.c_str());

	ImGui::SeparatorText("Select Input Video");
	if (ImGui::Button("Open File Browser")) {
		this->fileDialog.Open();
	}
 
	//ImGui::BeginChild();

	ImGui::End();	

	this->fileDialog.Display();

	if (this->fileDialog.HasSelected()) {
		std::cout << "get: " << this->fileDialog.GetSelected().string() << std::endl;
		this->fileDialog.ClearSelected();
	}
}
