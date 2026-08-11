#include "editor/ui/components/RunSelector.h"

#include "editor/ui/UIManager.h"

#include <algorithm>

#include <imgui.h>

void RunSelector::Render(const RunSetupData& data, std::vector<UIInput>& inputs) {
    bool openDeleteConfirmation = false;
    const std::size_t runCount = std::min({
        data.runNames.size(), data.runStatuses.size(), data.runIds.size()
    });

    if (runCount == 0) {
        ImGui::TextUnformatted("No existing runs");
    } else {
        ImGui::TextUnformatted("Existing Runs");
        if (ImGui::BeginTable("ExistingRuns", 2, ImGuiTableFlags_SizingStretchProp)) {
            ImGui::TableSetupColumn("Run", ImGuiTableColumnFlags_WidthStretch);
            ImGui::TableSetupColumn("Actions", ImGuiTableColumnFlags_WidthFixed);

            for (std::size_t index = 0; index < runCount; ++index) {
                const std::string label = data.runNames[index] + " (" + data.runStatuses[index] + ")";
                const bool canSelect = data.runStatuses[index] == "completed";

                ImGui::PushID(data.runIds[index].c_str());
                ImGui::TableNextRow();
                ImGui::TableSetColumnIndex(0);
                ImGui::BeginDisabled(!canSelect);
                if (ImGui::Selectable(label.c_str())) {
                    inputs.push_back({UIClick::SelectRun, data.runIds[index]});
                }
                ImGui::EndDisabled();

                ImGui::TableSetColumnIndex(1);
                if (ImGui::SmallButton("Delete")) {
                    pendingDeleteRunId_ = data.runIds[index];
                    pendingDeleteRunName_ = data.runNames[index];
                    openDeleteConfirmation = true;
                }
                ImGui::PopID();
            }
            ImGui::EndTable();
        }
    }

    if (openDeleteConfirmation) {
        ImGui::OpenPopup("Delete Run");
    }

    if (ImGui::BeginPopupModal("Delete Run", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::Text("Delete run \"%s\"?", pendingDeleteRunName_.c_str());
        ImGui::TextUnformatted("This action cannot be undone.");
        if (ImGui::Button("Delete")) {
            inputs.push_back({UIClick::DeleteRun, pendingDeleteRunId_});
            pendingDeleteRunId_.clear();
            pendingDeleteRunName_.clear();
            ImGui::CloseCurrentPopup();
        }
        ImGui::SameLine();
        if (ImGui::Button("Cancel")) {
            pendingDeleteRunId_.clear();
            pendingDeleteRunName_.clear();
            ImGui::CloseCurrentPopup();
        }
        ImGui::EndPopup();
    }
}
