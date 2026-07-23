#include "FileViewer.h"

#include "../../WorkspacePath.h"

FileViewer::FileViewer(String name, Phase phase) : UIPanel(name) {
	this->fileDialog = ImGui::FileBrowser(ImGuiFileBrowserFlags_Embedded | ImGuiFileBrowserFlags_NoModal);
	this->fileDialog.SetTypeFilters({ ".png", ".jpg", ".jpeg" });
	this->previewTexture = 0;
	this->phase = phase;

	switch (phase) {
		case Phase::CAPTURE: this->type = UIType::FILE_VIEWER_CAPTURE; break;
		case Phase::MASKING: this->type = UIType::FILE_VIEWER_MASKING; break;
		default: break;
	}
}

FileViewer::~FileViewer() {
    ClearPreview();
}

void FileViewer::Draw() {
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
	}

	ImGui::End();
}

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

void FileViewer::DrawBrowserTable() {
	if (ImGui::BeginTable("layout", 2, ImGuiTableFlags_BordersInnerV | ImGuiTableFlags_Resizable)) {
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

void FileViewer::ClearPreview() {
	if (this->previewTexture) {
		glDeleteTextures(1, &this->previewTexture);
		this->previewTexture = 0;
	}
	this->previewW = this->previewH = 0;
	this->lastPreviewPath.clear();
}

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

void FileViewer::SetWorkspaceToView(const std::filesystem::path& workspace) {
	this->hasRootFolder = false;
	this->workspace.clear();

	if (workspace.empty()) {
		std::cerr << "[ERROR] FileViewer::SetWorkspaceToView called with an empty workspace" << std::endl;
		return;
	}

	const std::filesystem::path phasePath = WorkspacePathForPhase(workspace, this->phase);
	if (phasePath.empty()) {
		std::cerr << "[ERROR] FileViewer has no workspace directory for its phase" << std::endl;
		return;
	}

	std::error_code ec;
	if (!std::filesystem::exists(phasePath, ec) || ec) {
		std::cerr << "[ERROR] Workspace phase path does not exist: " << phasePath << std::endl;
		return;
	}

	this->fileDialog.SetPwd(phasePath);
	this->workspace = workspace;
	this->hasRootFolder = true;
}

void FileViewer::ClearWorkspace() {
	this->workspace.clear();
	this->hasRootFolder = false;
	this->fileDialog.SetPwd(std::filesystem::current_path());
}

void FileViewer::ToggleRefresh(bool isRefreshing) {
	this->isRefreshing = isRefreshing;
}
