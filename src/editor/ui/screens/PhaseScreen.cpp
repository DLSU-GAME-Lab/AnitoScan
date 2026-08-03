#include "editor/ui/screens/PhaseScreen.h"

#include "editor/domain/RunState.h"

#include <imgui.h>

namespace {
const char* RunStatusText(RunStatus status) {
    switch (status) {
    case RunStatus::Pending:
        return "Pending";
    case RunStatus::Running:
        return "Running";
    case RunStatus::Completed:
        return "Completed";
    case RunStatus::Failed:
        return "Failed";
    case RunStatus::Cancelled:
        return "Cancelled";
    }

    return "Unknown";
}

const char* PipelinePhaseText(PipelinePhase phase) {
    switch (phase) {
    case PipelinePhase::Capture:
        return "Capture";
    case PipelinePhase::Masking:
        return "Masking";
    case PipelinePhase::Spatial:
        return "Spatial";
    case PipelinePhase::Geometry:
        return "Geometry";
    case PipelinePhase::Export:
        return "Export";
    }

    return "Unknown";
}
}

void PhaseScreen::Render(const RunState& run) {
    const ImGuiViewport* mainViewport = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(mainViewport->WorkPos);
    ImGui::SetNextWindowSize(mainViewport->WorkSize);

    constexpr ImGuiWindowFlags windowFlags =
        ImGuiWindowFlags_NoDecoration |
        ImGuiWindowFlags_NoMove |
        ImGuiWindowFlags_NoSavedSettings;

    ImGui::Begin("Pipeline", nullptr, windowFlags);
    ImGui::TextUnformatted("Pipeline");
    ImGui::Separator();
    ImGui::Text("Run: %s", run.name.c_str());
    ImGui::Text("Status: %s", RunStatusText(run.status));
    ImGui::Text("Phase: %s", PipelinePhaseText(run.phase));
    ImGui::End();
}
