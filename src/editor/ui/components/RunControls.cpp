#include "editor/ui/components/RunControls.h"

#include "editor/ui/UIStyle.h"

#include <imgui.h>

void RunControls::Render(
    const std::string& runId,
    const std::string& statusText,
    std::vector<UIInput>& inputs
) {
    if (statusText == "pending") {
        if (UIStyle::Button("Start", UIStyle::ButtonKind::Primary)) {
            inputs.push_back({UIClick::StartRun, runId});
        }
        ImGui::SameLine();
        if (UIStyle::Button("Cancel", UIStyle::ButtonKind::Danger)) {
            inputs.push_back({UIClick::CancelRun, runId});
        }
    } else if (statusText == "running") {
        if (UIStyle::Button("Cancel", UIStyle::ButtonKind::Danger)) {
            inputs.push_back({UIClick::CancelRun, runId});
        }
    } else if (statusText == "cancelling") {
        ImGui::TextUnformatted("Cancelling...");
    } else if (statusText == "completed" || statusText == "failed" || statusText == "cancelled") {
        if (UIStyle::Button("New Run", UIStyle::ButtonKind::Primary)) {
            inputs.push_back({UIClick::NewRun, {}});
        }
    }
}
