#include "editor/ui/components/RunControls.h"

#include "editor/controller/PipelineController.h"
#include "editor/domain/RunState.h"

#include <imgui.h>

void RunControls::Render(
    const RunState& run,
    bool backendReady,
    PipelineController& controller
) {
    if (run.status == RunStatus::Pending) {
        ImGui::BeginDisabled(!backendReady);
        if (ImGui::Button("Start")) {
            controller.StartRun(run.id);
        }
        ImGui::EndDisabled();
        if (!backendReady) {
            ImGui::SameLine();
            ImGui::TextUnformatted("Starting backend...");
        }
        ImGui::SameLine();
        if (ImGui::Button("Cancel")) {
            controller.CancelRun(run.id);
        }
    } else if (run.status == RunStatus::Running) {
        if (ImGui::Button("Cancel")) {
            controller.CancelRun(run.id);
        }
    } else if (run.status == RunStatus::Cancelling) {
        ImGui::TextUnformatted("Cancelling...");
    } else if (run.status == RunStatus::Completed || run.status == RunStatus::Failed ||
        run.status == RunStatus::Cancelled) {
        if (ImGui::Button("New Run")) {
            controller.ClearSelection();
        }
    }
}
