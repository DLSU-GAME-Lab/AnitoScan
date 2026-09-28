#include "editor/ui/components/RunSelector.h"

#include "editor/ui/UIManager.h"
#include "editor/ui/UIStyle.h"

#include <algorithm>

#include <imgui.h>

void RunSelector::Render(const RunSetupData& data, std::vector<UIInput>& inputs) {
    bool openDeleteConfirmation = false;
    const std::size_t runCount = std::min({
        data.runNames.size(), data.runStatuses.size(), data.runIds.size()
    });

    UIStyle::SectionTitle(
        "EXISTING RUNS",
        "Open completed results or remove runs you no longer need."
    );

    if (runCount == 0) {
        UIStyle::CenteredMessage("No existing runs", "Create a run to get started.");
    } else {
        constexpr ImGuiTableFlags tableFlags =
            ImGuiTableFlags_SizingStretchProp |
            ImGuiTableFlags_RowBg |
            ImGuiTableFlags_BordersInnerH;
        if (ImGui::BeginTable("ExistingRuns", 3, tableFlags)) {
            ImGui::TableSetupColumn("Run", ImGuiTableColumnFlags_WidthStretch);
            ImGui::TableSetupColumn("Status", ImGuiTableColumnFlags_WidthFixed, 112.0f);
            ImGui::TableSetupColumn("Actions", ImGuiTableColumnFlags_WidthFixed, 84.0f);
            ImGui::TableHeadersRow();

            for (std::size_t index = 0; index < runCount; ++index) {
                const bool canSelect = data.runStatuses[index] == "completed";

                ImGui::PushID(data.runIds[index].c_str());
                ImGui::TableNextRow();
                ImGui::TableSetColumnIndex(0);
                ImGui::BeginDisabled(!canSelect);
                const bool selected = ImGui::Selectable(
                    "##SelectRun",
                    false,
                    ImGuiSelectableFlags_None,
                    ImVec2(0.0f, ImGui::GetFrameHeight())
                );
                ImGui::EndDisabled();
                if (selected) {
                    inputs.push_back({UIClick::SelectRun, data.runIds[index]});
                }
                const ImVec2 itemMin = ImGui::GetItemRectMin();
                const ImVec2 itemMax = ImGui::GetItemRectMax();
                const ImVec2 textSize = ImGui::CalcTextSize(data.runNames[index].c_str());
                ImGui::GetWindowDrawList()->AddText(
                    ImVec2(itemMin.x + 12.0f, itemMin.y + (itemMax.y - itemMin.y - textSize.y) * 0.5f),
                    ImGui::GetColorU32(canSelect ? ImGuiCol_Text : ImGuiCol_TextDisabled),
                    data.runNames[index].c_str()
                );

                ImGui::TableSetColumnIndex(1);
                UIStyle::StatusBadge(data.runStatuses[index]);

                ImGui::TableSetColumnIndex(2);
                if (UIStyle::Button(
                    "Delete",
                    UIStyle::ButtonKind::Danger,
                    ImVec2(68.0f, 0.0f)
                )) {
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
        UIStyle::SectionTitle(
            "DELETE RUN",
            "This will permanently remove the selected run and its generated data."
        );
        ImGui::TextWrapped("Delete \"%s\"?", pendingDeleteRunName_.c_str());
        ImGui::TextDisabled("This action cannot be undone.");
        ImGui::Spacing();
        ImGui::Separator();
        ImGui::Spacing();

        constexpr float buttonWidth = 88.0f;
        const float actionWidth = buttonWidth * 2.0f + ImGui::GetStyle().ItemSpacing.x;
        ImGui::SetCursorPosX(std::max(
            ImGui::GetCursorPosX(),
            ImGui::GetWindowContentRegionMax().x - actionWidth
        ));
        if (UIStyle::Button(
            "Delete",
            UIStyle::ButtonKind::Danger,
            ImVec2(buttonWidth, 0.0f)
        )) {
            inputs.push_back({UIClick::DeleteRun, pendingDeleteRunId_});
            pendingDeleteRunId_.clear();
            pendingDeleteRunName_.clear();
            ImGui::CloseCurrentPopup();
        }
        ImGui::SameLine();
        if (UIStyle::Button(
            "Cancel",
            UIStyle::ButtonKind::Secondary,
            ImVec2(buttonWidth, 0.0f)
        )) {
            pendingDeleteRunId_.clear();
            pendingDeleteRunName_.clear();
            ImGui::CloseCurrentPopup();
        }
        ImGui::EndPopup();
    }
}
