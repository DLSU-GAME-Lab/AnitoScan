#include "editor/ui/screens/PostExportScreen.h"

#include "editor/domain/EditorState.h"

#include <imgui.h>

namespace {
const RunState* FindSelectedRun(const EditorState& state) {
    if (!state.selectedRunId) {
        return nullptr;
    }

    for (const RunState& run : state.runs) {
        if (run.id == *state.selectedRunId) {
            return &run;
        }
    }

    return nullptr;
}
}

void PostExportScreen::Render(const EditorState& state, unsigned int textureId) {
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

    const RunState* selectedRun = FindSelectedRun(state);
    const bool hasDisplayableModel = selectedRun != nullptr &&
        selectedRun->status == RunStatus::Completed && selectedRun->outputModelPath.has_value();
    viewport_.Render(hasDisplayableModel ? textureId : 0);
    ImGui::End();
}

int PostExportScreen::GetViewportWidth() const {
    return viewport_.GetWidth();
}

int PostExportScreen::GetViewportHeight() const {
    return viewport_.GetHeight();
}
