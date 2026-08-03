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
        creationError_.clear();
    }
    if (ImGui::Button("Create Run") && runName_[0] != '\0') {
        switch (controller.CreateRun(runName_.data())) {
        case CreateRunResult::Created:
            runName_.fill('\0');
            creationError_.clear();
            break;
        case CreateRunResult::DuplicateName:
            creationError_ = "A run with this name already exists";
            break;
        case CreateRunResult::InvalidName:
            creationError_ = "Run name contains invalid path characters";
            break;
        case CreateRunResult::StorageError:
            creationError_ = "Failed to save the run";
            break;
        }
    }
    if (!creationError_.empty()) {
        ImGui::TextColored(
            ImVec4(1.0f, 0.35f, 0.35f, 1.0f),
            "%s",
            creationError_.c_str()
        );
    }

    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Spacing();
    runSelector_.Render(state, controller);
    ImGui::End();
}
