#include "editor/ui/components/LogView.h"

#include <imgui.h>

void LogView::Render(const std::vector<std::string>& logs) {
    ImGui::Separator();
    ImGui::Text("Logs (%zu)", logs.size());
    const char* toggleLabel = expanded_ ? "Hide" : "Show";
    const float buttonWidth = ImGui::CalcTextSize(toggleLabel).x + ImGui::GetStyle().FramePadding.x * 2.0f;
    ImGui::SameLine(ImGui::GetContentRegionMax().x - buttonWidth);
    if (ImGui::Button(toggleLabel)) {
        expanded_ = !expanded_;
    }

    if (!expanded_) {
        return;
    }
    if (ImGui::BeginChild("Logs", ImVec2(0.0f, 150.0f), true)) {
        for (const std::string& log : logs) {
            ImGui::TextUnformatted(log.c_str());
        }
    }
    ImGui::EndChild();
}

float LogView::GetPreferredHeight() const {
    return expanded_ ? 190.0f : 34.0f;
}
