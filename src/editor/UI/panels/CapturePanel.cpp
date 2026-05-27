#include "CapturePanel.h"
#include <iostream>
#include <stb_image.h>

CapturePanel::CapturePanel() : UIPanel(UIType::CAPTURE_PANEL, "Capture") {
	this->fileDialog = ImGui::FileBrowser(ImGuiFileBrowserFlags_Embedded | ImGuiFileBrowserFlags_NoModal);
	this->fileDialog.SetTitle("FileBrowser");
	this->fileDialog.SetTypeFilters({ ".png", ".jpg", ".jpeg" });
	this->previewTexture = NULL;

	fileDialog.SetPwd(std::filesystem::current_path() / "data" / "runs" / "eevee_03" / "01_capture");
}


CapturePanel::~CapturePanel() {}


// top - file browser | bottom - preview section
void CapturePanel::DrawDefaultBrowser() {
	ImVec2 windowSize = ImGui::GetContentRegionAvail();
	float browserH = windowSize.y * 0.6f;
	float previewH = windowSize.y * 0.4f;

	ImGui::BeginChild("##browser", ImVec2(0, browserH), true);
	this->fileDialog.Display();
	ImGui::EndChild();

	if (this->fileDialog.HasSelected()) {
		LoadPreview(this->fileDialog.GetSelected().string());
		this->fileDialog.ClearSelected();
	}

	ImGui::Separator();
	ImGui::BeginChild("##preview", ImVec2(0, previewH), true);
	ImVec2 previewBox = ImGui::GetContentRegionAvail();
	if (this->previewTexture) 
		DrawFittedImage(this->previewTexture, this->previewW, this->previewH, previewBox);
	
	ImGui::EndChild();
}

// left - file browser | right - preview section
void CapturePanel::DrawBrowserTable() {
	if (ImGui::BeginTable("layout", 2,
		ImGuiTableFlags_BordersInnerV | ImGuiTableFlags_Resizable)) {

		ImGui::TableSetupColumn("Browser", ImGuiTableColumnFlags_WidthFixed, 300.0f);
		ImGui::TableSetupColumn("Preview", ImGuiTableColumnFlags_WidthStretch);

		ImGui::TableNextRow();
		ImGui::TableSetColumnIndex(0);
		this->fileDialog.Display();

		if (this->fileDialog.HasSelected()) {
			LoadPreview(this->fileDialog.GetSelected().string());
			this->fileDialog.ClearSelected();
		}

		ImGui::TableSetColumnIndex(1);
		ImVec2 previewBox = ImGui::GetContentRegionAvail();
		if (this->previewTexture)
			DrawFittedImage(this->previewTexture, this->previewW, this->previewH, previewBox);

		ImGui::EndTable();
	}
}


void CapturePanel::Draw() {
	ImGui::Begin(this->name.c_str());

	DrawDefaultBrowser();
	//DrawBrowserTable();

	ImGui::End();
}


void CapturePanel::LoadPreview(const std::string& path) {
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

void CapturePanel::ClearPreview() {
	if (this->previewTexture) {
		glDeleteTextures(1, &this->previewTexture);
		this->previewTexture = 0;
	}
	this->previewW = this->previewH = 0;
	this->lastPreviewPath.clear();
}


// display 
void CapturePanel::DrawFittedImage(GLuint texture, int imgW, int imgH, ImVec2 availSpace) {
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
