#include "editor/ui/screens/PhaseScreen.h"

#include "editor/controller/PipelineController.h"
#include "editor/domain/RunState.h"

#include <imgui.h>

namespace {
const char* RunStatusText(RunStatus status) {
    switch (status) {
    case RunStatus::Pending:
        return "Pending";
    case RunStatus::Running:
        return "Running";
    case RunStatus::Cancelling:
        return "Cancelling";
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

void PhaseScreen::Render(
    const RunState& run,
    bool backendReady,
    const std::vector<std::string>& logs,
    PipelineController& controller
) {
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
    if (run.status == RunStatus::Running) {
        ImGui::TextUnformatted(run.progressLabel.c_str());
        ImGui::ProgressBar(run.progress);
    }
    maskingContent_.Render(run, controller);
    if (run.errorMessage) {
        ImGui::TextColored(
            ImVec4(1.0f, 0.35f, 0.35f, 1.0f),
            "%s",
            run.errorMessage->c_str()
        );
    }
    ImGui::Separator();
    logView_.Render(logs);
    ImGui::Separator();
    runControls_.Render(run, backendReady, controller);
    ImGui::End();
}

void PhaseScreen::Shutdown() {
    maskingContent_.Shutdown();
}
