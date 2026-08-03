#include "editor/ui/components/RunSelector.h"

#include "editor/controller/PipelineController.h"
#include "editor/domain/EditorState.h"

#include <string>

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
}

void RunSelector::Render(const EditorState& state, PipelineController& controller) {
    if (state.runs.empty()) {
        ImGui::TextUnformatted("No existing runs");
        return;
    }

    ImGui::TextUnformatted("Existing Runs");
    for (const RunState& run : state.runs) {
        const std::string label = run.name + " (" + RunStatusText(run.status) + ")";
        ImGui::PushID(run.id.c_str());
        if (ImGui::Selectable(label.c_str())) {
            controller.SelectRun(run.id);
        }
        ImGui::PopID();
    }
}
