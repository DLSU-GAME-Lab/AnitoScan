#include "editor/ui/components/RunControls.h"

#include <imgui.h>

void RunControls::Render(
    const std::string& runId,
    const std::string& statusText,
    std::vector<UIInput>& inputs
) {
    if (statusText == "pending") {
        if (ImGui::Button("Start")) {
            inputs.push_back({UIClick::StartRun, runId});
        }
        ImGui::SameLine();
        if (ImGui::Button("Cancel")) {
            inputs.push_back({UIClick::CancelRun, runId});
        }
    } else if (statusText == "running") {
        if (ImGui::Button("Cancel")) {
            inputs.push_back({UIClick::CancelRun, runId});
        }
    } else if (statusText == "cancelling") {
        ImGui::TextUnformatted("Cancelling...");
    } else if (statusText == "failed" || statusText == "cancelled") {
        if (ImGui::Button("New Run")) {
            inputs.push_back({UIClick::NewRun, {}});
        }
    }
}
