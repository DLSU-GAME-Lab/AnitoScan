#include "editor/ui/screens/RunSetupScreen.h"

#include "editor/controller/PipelineController.h"
#include "editor/domain/EditorState.h"

#include <imgui.h>

void RunSetupScreen::Render(const EditorState& state, PipelineController& controller) {
    const ImGuiViewport* mainViewport = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(mainViewport->WorkPos);
    ImGui::SetNextWindowSize(mainViewport->WorkSize);

    constexpr ImGuiWindowFlags windowFlags =
        ImGuiWindowFlags_NoDecoration |
        ImGuiWindowFlags_NoMove |
        ImGuiWindowFlags_NoSavedSettings;

    ImGui::Begin("Run Setup", nullptr, windowFlags);
    ImGui::TextUnformatted("Run Setup");
    ImGui::Separator();
    ImGui::InputText("Run name", runName_.data(), runName_.size());
    if (ImGui::Button("Create Run") && runName_[0] != '\0') {
        controller.CreateRun(runName_.data());
        runName_.fill('\0');
    }

    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Spacing();
    runSelector_.Render(state, controller);
    ImGui::End();
}
