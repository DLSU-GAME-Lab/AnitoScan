#include "ViewportPanel.h"

ViewportPanel::ViewportPanel(String name, Scene& scene, const EditorState& state)
    : UIPanel(UIType::VIEWPORT, name), scene(scene), state(state) {}

ViewportPanel::~ViewportPanel() {}

void ViewportPanel::Draw() {
    if (!state.pipeline.latestOutput.empty() && state.pipeline.latestOutput != loadedModelPath) {
        this->scene.LoadModel(state.pipeline.latestOutput);
        this->loadedModelPath = state.pipeline.latestOutput;
    }

    ImGuiWindowFlags flags = ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoResize;
	ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(0, 0));
	ImGui::Begin(this->name.c_str(), nullptr, flags);

	hoveredLastFrame = ImGui::IsWindowHovered();

	ImVec2 panelSize = ImGui::GetContentRegionAvail();

    if (panelSize.x > 0 && panelSize.y > 0) {
        this->scene.Render(static_cast<int>(panelSize.x), static_cast<int>(panelSize.y));

        GLuint tex = this->scene.GetColorTexture();
        if (tex != 0) {
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
