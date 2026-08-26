#include "editor/ui/screens/PhaseScreen.h"

#include "editor/ui/UIManager.h"

#include <algorithm>

#include <imgui.h>

void PhaseScreen::Render(const PhaseDisplayData& data, std::vector<UIInput>& inputs) {
    const ImGuiViewport* mainViewport = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(mainViewport->WorkPos);
    ImGui::SetNextWindowSize(mainViewport->WorkSize);

    constexpr ImGuiWindowFlags windowFlags =
        ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoSavedSettings;
    ImGui::Begin("Pipeline", nullptr, windowFlags);

    if (ImGui::BeginTable("Header", 2, ImGuiTableFlags_SizingStretchProp)) {
        ImGui::TableSetupColumn("Run", ImGuiTableColumnFlags_WidthStretch);
        ImGui::TableSetupColumn("Actions", ImGuiTableColumnFlags_WidthFixed);
        ImGui::TableNextColumn();
        ImGui::TextUnformatted(data.runName.c_str());
        ImGui::TextDisabled("%s", data.statusText.c_str());
        ImGui::TableNextColumn();
        runControls_.Render(data.runId, data.statusText, inputs);
        ImGui::EndTable();
    }

    ImGui::Separator();
    ImGui::BeginDisabled(!data.navigation.canGoBack);
    if (ImGui::Button("Back")) {
        inputs.push_back({UIClick::PreviousPhase, {}});
    }
    ImGui::EndDisabled();

    if (data.navigation.viewingLatest) {
        ImGui::SameLine();
        ImGui::BeginDisabled();
        ImGui::Button("Live");
        ImGui::EndDisabled();
    } else {
        if (data.navigation.canGoNext) {
            ImGui::SameLine();
            if (ImGui::Button("Next")) {
                inputs.push_back({UIClick::NextPhase, {}});
            }
        }
        if (data.navigation.canFollowLive) {
            ImGui::SameLine();
            if (ImGui::Button("Follow Live")) {
                inputs.push_back({UIClick::FollowLive, {}});
            }
        }
    }
    if (!data.phaseText.empty()) {
        ImGui::SameLine();
        ImGui::TextDisabled("Phase: %s", data.phaseText.c_str());
    }
    ImGui::Separator();

    const float footerHeight = logView_.GetPreferredHeight();
    const float mainHeight = std::max(0.0f, ImGui::GetContentRegionAvail().y - footerHeight);
    if (ImGui::BeginChild("PhaseContent", ImVec2(0.0f, mainHeight), false)) {
        switch (data.kind) {
        case PhaseDisplayKind::Loading:
            ImGui::TextDisabled("Loading...");
            break;
        case PhaseDisplayKind::Processing:
            ImGui::TextDisabled("Processing...");
            break;
        case PhaseDisplayKind::Progress:
            if (!data.phaseText.empty()) {
                ImGui::TextUnformatted(data.phaseText.c_str());
            }
            if (!data.progressText.empty()) {
                ImGui::TextUnformatted(data.progressText.c_str());
            }
            ImGui::ProgressBar(std::clamp(data.progress, 0.0f, 1.0f), ImVec2(-1.0f, 0.0f));
            break;
        case PhaseDisplayKind::MaskSelection:
            maskingContent_.Render(
                data.previewPath,
                data.candidateCount,
                data.maskSelectionEnabled,
                inputs
            );
            break;
        case PhaseDisplayKind::Error:
            ImGui::TextColored(ImVec4(1.0f, 0.35f, 0.35f, 1.0f), "%s", data.errorText.c_str());
            break;
        }
    }
    ImGui::EndChild();
    logView_.Render(data.logs);
    ImGui::End();
}

void PhaseScreen::Shutdown() {
    maskingContent_.Shutdown();
}
