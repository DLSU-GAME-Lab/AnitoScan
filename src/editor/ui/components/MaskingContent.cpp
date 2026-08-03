#include "editor/ui/components/MaskingContent.h"

#include "editor/controller/PipelineController.h"
#include "editor/domain/RunState.h"

#include <algorithm>
#include <optional>
#include <string>

#include <imgui.h>

void MaskingContent::Render(const RunState& run, PipelineController& controller) {
    if (!run.selectionRequest) {
        return;
    }

    const SelectionRequest& request = *run.selectionRequest;
    ImGui::Separator();
    ImGui::Text("Frame: %s", request.frame.c_str());
    ImGui::Text("Preview: %s", request.previewPath.string().c_str());

    const int candidateCount = std::max(0, request.candidateCount);
    for (int candidate = 0; candidate < candidateCount; ++candidate) {
        const std::string label = "Candidate " + std::to_string(candidate);
        if (ImGui::Button(label.c_str())) {
            controller.SubmitSelection(run.id, candidate);
        }
        if (candidate + 1 < candidateCount) {
            ImGui::SameLine();
        }
    }

    if (ImGui::Button("Skip")) {
        controller.SubmitSelection(run.id, std::nullopt);
    }
}
