#include "MaskingPopup.h"

MaskingPopup::MaskingPopup(String name, IPCClient& ipc)
    : UIPanel(UIType::MASKING_MODAL, name, false), ipc(ipc) {
	this->lastPreviewPath = "";
	this->previewTexture = NULL;
	this->showPopup = activeSelf;
}

MaskingPopup::~MaskingPopup() {}

void MaskingPopup::Draw() {
    if (this->showPopup) {
        ImGui::OpenPopup(this->GetName().c_str());
        this->showPopup = false;
    }

    ImVec2 center = ImGui::GetMainViewport()->GetCenter();
    ImGui::SetNextWindowPos(center, ImGuiCond_Always, ImVec2(0.5f, 0.5f));
    ImGui::SetNextWindowSize(ImVec2(1000, 700), ImGuiCond_Always);

    ImGuiWindowFlags popupflags = ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove;

    if (ImGui::BeginPopupModal(this->GetName().c_str(), nullptr, popupflags)) {
        ImGui::Text("Frame: %s", this->frame.c_str());
        ImGui::Text("Select the correct subject:");
        ImGui::Separator();

        if (this->previewTexture) {
            DisplayPreview();
        }
        else {
            ImGui::TextDisabled("Loading preview...");
        }

        ImGui::Separator();

        DisplayCandidatesButton();
        DisplaySkipButton();

        ImGui::EndPopup();
    }
}

void MaskingPopup::ShowCandidates(String requestId, String previewPath, String frame, int count) {
	this->requestId = requestId;
	this->count = count;
	this->frame = frame;

    ShowPopup();
	LoadPreview(previewPath);
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

	glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
	glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
	glPixelStorei(GL_UNPACK_SKIP_PIXELS, 0);
	glPixelStorei(GL_UNPACK_SKIP_ROWS, 0);

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

void MaskingPopup::DisplayPreview() {
    ImVec2 availSize = ImVec2(960, 540);
    float aspect = (float)this->previewH / (float)this->previewW;
    float baseW = availSize.x;
    float baseH = baseW * aspect;
    if (baseH > availSize.y) {
        baseH = availSize.y;
        baseW = baseH / aspect;
    }

    ImVec2 displaySize(baseW * this->zoom, baseH * this->zoom);

    ImGui::BeginChild("##preview_zoom", availSize, false, ImGuiWindowFlags_NoScrollbar | ImGuiWindowFlags_NoScrollWithMouse);

    ImVec2 centerOff = ImVec2((availSize.x - displaySize.x) * 0.5f + this->panOffset.x,
        (availSize.y - displaySize.y) * 0.5f + this->panOffset.y);

    ImGui::SetCursorPos(centerOff);
    ImGui::Image((ImTextureID)(intptr_t)this->previewTexture, displaySize);

    if (ImGui::IsWindowHovered(ImGuiHoveredFlags_ChildWindows)) {
        float wheel = ImGui::GetIO().MouseWheel;
        if (wheel != 0.0f) {
            float zoomFactor = 1.0f + wheel * 0.1f;
            this->zoom = std::clamp(this->zoom * zoomFactor, 0.5f, 5.0f);
        }

        if (ImGui::IsMouseDragging(ImGuiMouseButton_Left)) {
            ImVec2 delta = ImGui::GetIO().MouseDelta;
            this->panOffset.x += delta.x;
            this->panOffset.y += delta.y;
        }
    }
    ImGui::EndChild();

    ImGui::Text("Zoom: %.0f%%", this->zoom * 100.0f);
    ImGui::SameLine();
    if (ImGui::Button("Reset")) {
        this->zoom = 1.0f;
        this->panOffset = ImVec2(0, 0);
    }
    ImGui::SameLine();
    ImGui::TextDisabled("(scroll to zoom, drag to pan)");
}

void MaskingPopup::DisplayCandidatesButton() {
    for (int i = 0; i < this->count; i++) {
        String label = "  " + std::to_string(i) + "  ";
        if (ImGui::Button(label.c_str(), ImVec2(60, 36))) {
            std::string cmd = IPCProtocol::SerializeSelection(this->requestId, i);
            this->ipc.Send(cmd);
            ImGui::CloseCurrentPopup();
        }
        ImGui::SameLine();
    }
}

void MaskingPopup::DisplaySkipButton() {
    if (ImGui::Button("Skip", ImVec2(60, 36))) {
        std::string cmd = IPCProtocol::SerializeSelectionSkip(this->requestId);
        this->ipc.Send(cmd);
        ImGui::CloseCurrentPopup();
    }
}
