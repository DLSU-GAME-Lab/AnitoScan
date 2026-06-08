#include "MaskingPopup.h"

MaskingPopup::MaskingPopup(String name) : UIPanel(UIType::MASKING_MODAL, name, false) {
	this->lastPreviewPath = "";
	this->previewTexture = NULL;
	this->showPopup = activeSelf;
}

MaskingPopup::~MaskingPopup() {}

void MaskingPopup::Draw() {
	if (this->showPopup) {
		ImGui::OpenPopup(this->GetName().c_str());
		this->showPopup = false;
		//this->activeSelf 
	}


	ImGuiWindowFlags flags = ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoMove;
	ImVec2 size = ImVec2(1000, 700.0f);

	ImVec2 center = ImGui::GetMainViewport()->GetCenter();
	ImGui::SetNextWindowSize(size, ImGuiCond_Always);
	ImGui::SetNextWindowPos(center, ImGuiCond_Appearing, ImVec2(0.5f, 0.5f));
	if (ImGui::BeginPopupModal(this->GetName().c_str(), nullptr, flags)) {
		//ImGui::Dummy(ImVec2(300.0f, 0.0f));

		// 2. Pass the ImGuiWindowFlags_NoResize flag into Begin()
		ImGui::Image((ImTextureID)(intptr_t)this->previewTexture, size);

		if (ImGui::Button("Close")) {
			ImGui::CloseCurrentPopup();
		}

		ImGui::EndPopup();
	}

	//ImGui::End();

}

void MaskingPopup::InitializeEntryFiles() {
	OverviewPanel* panel = (OverviewPanel*)UIManager::GetInstance()->GetPanelByType(UIType::OVERVIEW);
	std::filesystem::path path = std::filesystem::current_path() / "data" / "runs" / panel->GetOutputFolder() / "02_masking" / "temp";

	if (std::filesystem::exists(path) && std::filesystem::is_directory(path)) {
		for (const auto& entry : std::filesystem::directory_iterator(path)) {
			if (entry.is_regular_file()) {
				this->entryFiles.push_back(entry.path());
			}
		}
	}
}

void MaskingPopup::SetImagePreview(int index) {
	if (index < this->entryFiles.size()) {
		LoadPreview(this->entryFiles[index].string());
	}
}

void MaskingPopup::ShowPopup() {
	this->activeSelf = true;
	this->showPopup = true;
}

void MaskingPopup::LoadPreview(const String& path) {
	if (path == this->lastPreviewPath) return;
	ClearPreview();

	int channels;
	unsigned char* data = stbi_load(path.c_str(), &this->previewW, &this->previewH, &channels, 4);

	if (!data) {
		std::cerr << "[ERROR] Loaded image data not found." << std::endl;
		return;
	}

	glGenTextures(1, &this->previewTexture);
	glBindTexture(GL_TEXTURE_2D, this->previewTexture);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, this->previewW, this->previewH, 0, GL_RGBA, GL_UNSIGNED_BYTE, data);
	stbi_image_free(data);
	this->lastPreviewPath = path;
}


void MaskingPopup::ClearPreview() {
	if (this->previewTexture) {
		glDeleteTextures(1, &this->previewTexture);
		this->previewTexture = 0;
	}
	this->previewW = this->previewH = 0;
	this->lastPreviewPath.clear();
}


void MaskingPopup::DrawFittedImage(GLuint texture, int imgW, int imgH, ImVec2 availSpace) {
	float scaleX = availSpace.x / (float)imgW;
	float scaleY = availSpace.y / (float)imgH;
	float scale = std::min(scaleX, scaleY);

	ImVec2 displaySize(imgW * scale, imgH * scale);

	ImVec2 cursor = ImGui::GetCursorPos();
	float offsetX = (availSpace.x - displaySize.x) * 0.5f;
	float offsetY = (availSpace.y - displaySize.y) * 0.5f;
	ImGui::SetCursorPos(ImVec2(cursor.x + offsetX, cursor.y + offsetY));

	ImGui::Image((ImTextureID)(intptr_t)texture, displaySize);
}