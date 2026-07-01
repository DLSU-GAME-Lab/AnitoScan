#include "MaskingPopup.h"

//Initializes the popup's UI properties, default preview texture states, and binds the IPC client reference
MaskingPopup::MaskingPopup(String name, IPCClient& ipc) 
    : UIPanel(UIType::MASKING_MODAL, name, false), ipc(ipc) {
	this->lastPreviewPath = "";
	this->previewTexture = NULL;
	this->showPopup = activeSelf;
}

MaskingPopup::~MaskingPopup() {}


// Handles the core rendering loop for the popup modal and draws the image preview alongside its action buttons.
void MaskingPopup::Draw() {
    if (this->showPopup) {
        ImGui::OpenPopup(this->GetName().c_str());
        this->showPopup = false;
    }

    // center the window
    ImVec2 center = ImGui::GetMainViewport()->GetCenter();
    ImGui::SetNextWindowPos(center, ImGuiCond_Always, ImVec2(0.5f, 0.5f));
    ImGui::SetNextWindowSize(ImVec2(1000, 700), ImGuiCond_Always);

    ImGuiWindowFlags popupflags = ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove;

    // draw window
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

        // candidates button
        DisplayCandidatesButton();

        // skip button
        DisplaySkipButton();

        ImGui::EndPopup();
    }
}

// Prepares and activates the popup to display a specfic image. 
// Flags the UI to open and loads the target preview image
void MaskingPopup::ShowCandidates(String previewPath, String frame, int count) {
	this->count = count;
	this->frame = frame;

    ShowPopup();
	LoadPreview(previewPath);
}

// Activates the popup window
void MaskingPopup::ShowPopup() {
	this->activeSelf = true;
	this->showPopup = true;
}

// Loads the image to be examined via stb_image, configures GL filters, and binds texture ID for ImGui rendering
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

// Preview cleanup
void MaskingPopup::ClearPreview() {
    if (this->previewTexture) {
        glDeleteTextures(1, &this->previewTexture);
        this->previewTexture = 0;
    }
    this->previewW = this->previewH = 0;
    this->lastPreviewPath.clear();
}

// Renders the loaded texture and handles mouse wheel zoom and left-drag panning interactions
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

    ImVec2 childPos = ImGui::GetCursorScreenPos();
    ImVec2 centerOff = ImVec2((availSize.x - displaySize.x) * 0.5f + this->panOffset.x,
        (availSize.y - displaySize.y) * 0.5f + this->panOffset.y);

    ImGui::SetCursorPos(centerOff);
    ImGui::Image((ImTextureID)(intptr_t)this->previewTexture, displaySize);

    //zoom function
    if (ImGui::IsWindowHovered(ImGuiHoveredFlags_ChildWindows)) {
        float wheel = ImGui::GetIO().MouseWheel;
        if (wheel != 0.0f) {
            float zoomFactor = 1.0f +
                wheel * 0.1f;
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
        ;
    }
    ImGui::SameLine();
    ImGui::TextDisabled("(scroll to zoom, drag to pan)");
}

// Renders a dynamic row of numbered selection buttons for candidates and sends a response over the IPC
void MaskingPopup::DisplayCandidatesButton() {
    for (int i = 0; i < this->count; i++) {
        String label = "  " + std::to_string(i) + "  ";
        if (ImGui::Button(label.c_str(), ImVec2(60, 36))) {
            nlohmann::json response;
            response["type"] = "selection";
            response["choice"] = std::to_string(i);
            this->ipc.Send(response.dump());
            ImGui::CloseCurrentPopup();
        }
        ImGui::SameLine();
    }
}

// Renders a skip button for the candidate selection and broadcasts it over IPC
void MaskingPopup::DisplaySkipButton() {
    if (ImGui::Button("Skip", ImVec2(60, 36))) {
        nlohmann::json response;
        response["type"] = "selection";
        response["choice"] = "skip";
        this->ipc.Send(response.dump());
        ImGui::CloseCurrentPopup();
    }
}