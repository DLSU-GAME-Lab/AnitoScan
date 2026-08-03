#include "editor/ui/components/LogView.h"

#include <imgui.h>

void LogView::Render(const std::vector<std::string>& logs) {
    ImGui::TextUnformatted("Logs");
    if (ImGui::BeginChild("Logs", ImVec2(0.0f, 160.0f), true)) {
        for (const std::string& log : logs) {
            ImGui::TextUnformatted(log.c_str());
        }
    }
    ImGui::EndChild();
}
