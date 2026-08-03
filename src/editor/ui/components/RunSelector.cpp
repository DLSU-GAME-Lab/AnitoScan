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
    bool openDeleteConfirmation = false;

    if (state.runs.empty()) {
        ImGui::TextUnformatted("No existing runs");
    } else {
        ImGui::TextUnformatted("Existing Runs");
        if (ImGui::BeginTable("ExistingRuns", 2, ImGuiTableFlags_SizingStretchProp)) {
            ImGui::TableSetupColumn("Run", ImGuiTableColumnFlags_WidthStretch);
            ImGui::TableSetupColumn("Actions", ImGuiTableColumnFlags_WidthFixed);

            for (const RunState& run : state.runs) {
                const std::string label = run.name + " (" + RunStatusText(run.status) + ")";
                const bool canDelete =
                    run.status != RunStatus::Running && run.status != RunStatus::Cancelling;

                ImGui::PushID(run.id.c_str());
                ImGui::TableNextRow();
                ImGui::TableSetColumnIndex(0);
                if (ImGui::Selectable(label.c_str())) {
                    controller.SelectRun(run.id);
                }

                ImGui::TableSetColumnIndex(1);
                if (canDelete && ImGui::SmallButton("Delete")) {
                    pendingDeleteRunId_ = run.id;
                    pendingDeleteRunName_ = run.name;
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
            controller.DeleteRun(pendingDeleteRunId_);
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
