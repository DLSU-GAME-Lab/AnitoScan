#include "editor/ui/screens/PostExportScreen.h"

#include "editor/controller/PipelineController.h"

#include <imgui.h>

void PostExportScreen::Render(unsigned int textureId, PipelineController& controller) {
    const ImGuiViewport* mainViewport = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(mainViewport->WorkPos);
    ImGui::SetNextWindowSize(mainViewport->WorkSize);

    constexpr ImGuiWindowFlags windowFlags =
        ImGuiWindowFlags_NoDecoration |
        ImGuiWindowFlags_NoMove |
        ImGuiWindowFlags_NoSavedSettings;

    ImGui::Begin("Post Export", nullptr, windowFlags);
    ImGui::TextUnformatted("Post Export");
    ImGui::Separator();
    if (ImGui::Button("New Run")) {
        controller.ClearSelection();
    }

    viewport_.Render(textureId);
    ImGui::End();
}

int PostExportScreen::GetViewportWidth() const {
    return viewport_.GetWidth();
}

int PostExportScreen::GetViewportHeight() const {
    return viewport_.GetHeight();
}
