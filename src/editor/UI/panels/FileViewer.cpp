#include "FileViewer.h"

// Configures the embedded file browser flags and filters out image format extensions for browsing
FileViewer::FileViewer(String name, Phase phase) : UIPanel(name) {
	this->fileDialog = ImGui::FileBrowser(ImGuiFileBrowserFlags_Embedded | ImGuiFileBrowserFlags_NoModal);
	//this->fileDialog.SetTitle("FileBrowser");
	this->fileDialog.SetTypeFilters({ ".png", ".jpg", ".jpeg" });
	this->previewTexture = NULL;
	this->phase = phase;

	switch (phase) {
		case Phase::CAPTURE: this->type = UIType::FILE_VIEWER_CAPTURE; break;
		case Phase::MASKING: this->type = UIType::FILE_VIEWER_MASKING; break;
	}
}

FileViewer::~FileViewer() {}

// Manages a refresh timer to poll the storage directory for changes and calls the draw function for the browser
void FileViewer::Draw() {
	//update timer
	ImGuiIO& io = ImGui::GetIO();

	if (this->isRefreshing) {
		this->refreshTimer += io.DeltaTime;
		if (this->refreshTimer >= this->refreshInterval) {
			this->fileDialog.Refresh();
			this->refreshTimer = 0.0f;
		}
	}

	ImGui::Begin(this->name.c_str());

	if (this->hasRootFolder) {
		DrawDefaultBrowser();
		//DrawBrowserTable();
	}

	ImGui::End();
}

// Displays the directory and preview panel in a vertical layout
void FileViewer::DrawDefaultBrowser() {
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

// Displays the directory and preview panel side-by-side
void FileViewer::DrawBrowserTable() {
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

// Decodes an image file into memory and uploads it as a 2D OpenGL texture via stb_image
void FileViewer::LoadPreview(const String& path) {
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

	glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
	glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
	glPixelStorei(GL_UNPACK_SKIP_PIXELS, 0);
	glPixelStorei(GL_UNPACK_SKIP_ROWS, 0);

	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, this->previewW, this->previewH, 0, GL_RGBA, GL_UNSIGNED_BYTE, data);
	stbi_image_free(data);
	this->lastPreviewPath = path;
}

// Preview image clean up
void FileViewer::ClearPreview() {
	if (this->previewTexture) {
		glDeleteTextures(1, &this->previewTexture);
		this->previewTexture = 0;
	}
	this->previewW = this->previewH = 0;
	this->lastPreviewPath.clear();
}

// Computes aspect ratio uniform scaling and positions the image in the center of the viewport box
// Shifts ImGui rendering cursors to center align, and draws the output texture
void FileViewer::DrawFittedImage(GLuint texture, int imgW, int imgH, ImVec2 availSpace) {
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

// Evaluates and targets a specific subdirectory run folder depending on the active stage process
void FileViewer::SetOutputFolderToView(std::filesystem::path output) {
	if (output.empty()) {
		std::cerr << "[ERROR] FileViewer::SetRootFolderToView called with empty root" << std::endl;
		return;
	}

	this->output = output;
	this->hasRootFolder = true;

	std::filesystem::path temp;
	switch(this->phase) {
		case Phase::CAPTURE: temp = "01_capture"; break;
		case Phase::MASKING: temp = "02_masking"; break;
		case Phase::SPATIAL: temp = "03_spatial"; break;
	}

	//std::filesystem::path fullPath = std::filesystem::current_path() / "data" / "runs" / this->output / temp;

	std::filesystem::path projectRoot(PROJECT_ROOT_DIR);
	std::filesystem::path fullPath = projectRoot / "data" / "runs" / this->output / temp;

	std::error_code ec;
	if (!std::filesystem::exists(fullPath, ec)) {
		std::cerr << "[ERROR] Path does not exist: " << fullPath << std::endl;
		return;
	}

	this->fileDialog.SetPwd(fullPath);

}

void FileViewer::ClearOutputFolder() {
	this->output.clear();
	this->hasRootFolder = false;
	this->fileDialog.SetPwd(std::filesystem::current_path());
}

// Controls whether the file dialog should continuously trigger directory polling updates inside the frame loop
void FileViewer::ToggleRefresh(bool isRefreshing) {
	this->isRefreshing = isRefreshing;
}
