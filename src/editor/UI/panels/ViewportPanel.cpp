#include "ViewportPanel.h"

ViewportPanel::ViewportPanel(String name, Scene& scene) 
	: UIPanel(UIType::VIEWPORT, name), scene(scene) {
    this->scene.LoadModel("data/output/GROOT_CHECK/groot.obj"); //PLACEHOLDER
}

ViewportPanel::~ViewportPanel() {}

// Displays the model viewer panel
void ViewportPanel::Draw() {
    ImGuiWindowFlags flags = ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoResize;

	ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(0, 0));
	ImGui::Begin(this->name.c_str(), nullptr, flags);

	hoveredLastFrame = ImGui::IsWindowHovered();

	ImVec2 panelSize = ImGui::GetContentRegionAvail();

    if (panelSize.x > 0 && panelSize.y > 0) {
        this->scene.Render(static_cast<int>(panelSize.x), static_cast<int>(panelSize.y));

        GLuint tex = this->scene.GetColorTexture();
        if (tex != 0) {
            // flipped UVs
            ImGui::Image(static_cast<ImTextureID>(tex),
                panelSize, ImVec2(0, 1), ImVec2(1, 0));
        }
    }

    ImGui::End();
    ImGui::PopStyleVar();
}

bool ViewportPanel::IsHovered() {
	return this->hoveredLastFrame;
}