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
    if (ImGui::InputText("Run name", runName_.data(), runName_.size())) {
        duplicateName_ = false;
    }
    if (ImGui::Button("Create Run") && runName_[0] != '\0') {
        if (controller.CreateRun(runName_.data())) {
            runName_.fill('\0');
            duplicateName_ = false;
        } else {
            duplicateName_ = true;
        }
    }
    if (duplicateName_) {
        ImGui::TextColored(
            ImVec4(1.0f, 0.35f, 0.35f, 1.0f),
            "A run with this name already exists"
        );
    }

    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Spacing();
    runSelector_.Render(state, controller);
    ImGui::End();
}
