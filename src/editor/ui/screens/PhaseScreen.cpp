#include "editor/ui/screens/PhaseScreen.h"

#include "editor/ui/UIManager.h"
#include "editor/ui/UIStyle.h"

#include <algorithm>
#include <string>

#include <imgui.h>

void PhaseScreen::Render(const PhaseDisplayData& data, std::vector<UIInput>& inputs) {
    if (data.kind != PhaseDisplayKind::MaskSelection) {
        ResetInteraction();
    } else {
        maskingContent_.UpdateInteraction(data);
    }
    const ImGuiViewport* mainViewport = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(mainViewport->WorkPos);
    ImGui::SetNextWindowSize(mainViewport->WorkSize);

    constexpr ImGuiWindowFlags windowFlags =
        ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoSavedSettings;
    ImGui::Begin("Pipeline", nullptr, windowFlags);

    if (ImGui::BeginChild("PipelineHeader", ImVec2(0.0f, 92.0f), true, ImGuiWindowFlags_NoScrollbar)) {
        if (ImGui::BeginTable("Header", 2, ImGuiTableFlags_SizingStretchProp)) {
            ImGui::TableSetupColumn("Run", ImGuiTableColumnFlags_WidthStretch);
            ImGui::TableSetupColumn("Actions", ImGuiTableColumnFlags_WidthFixed);
            ImGui::TableNextColumn();
            ImGui::TextDisabled("ANITOSCAN / PIPELINE");
            ImGui::SetWindowFontScale(1.18f);
            ImGui::TextUnformatted(data.runName.c_str());
            ImGui::SetWindowFontScale(1.0f);
            ImGui::SameLine();
            UIStyle::StatusBadge(data.statusText);
            ImGui::TableNextColumn();
            ImGui::Dummy(ImVec2(0.0f, 10.0f));
            runControls_.Render(data.runId, data.statusText, inputs);
            ImGui::EndTable();
        }
    }
    ImGui::EndChild();
    ImGui::Spacing();

    if (ImGui::BeginChild("PhaseToolbar", ImVec2(0.0f, 60.0f), true, ImGuiWindowFlags_NoScrollbar)) {
        ImGui::BeginDisabled(!data.navigation.canGoBack);
        if (UIStyle::Button("Back", UIStyle::ButtonKind::Secondary)) {
            inputs.push_back({UIClick::PreviousPhase, {}});
        }
        ImGui::EndDisabled();

        if (data.navigation.viewingLatest) {
            ImGui::SameLine();
            if (data.navigation.canStopFollowingLive) {
                if (UIStyle::Button("Stop Following Live", UIStyle::ButtonKind::Ghost)) {
                    inputs.push_back({UIClick::StopFollowingLive, {}});
                }
            } else {
                ImGui::BeginDisabled();
                UIStyle::Button("Live", UIStyle::ButtonKind::Ghost);
                ImGui::EndDisabled();
            }
        } else {
            if (data.navigation.canGoNext) {
                ImGui::SameLine();
                if (UIStyle::Button("Next", UIStyle::ButtonKind::Secondary)) {
                    inputs.push_back({UIClick::NextPhase, {}});
                }
            }
            if (data.navigation.canFollowLive) {
                ImGui::SameLine();
                if (UIStyle::Button("Follow Live", UIStyle::ButtonKind::Primary)) {
                    inputs.push_back({UIClick::FollowLive, {}});
                }
            }
        }

        if (!data.phaseText.empty()) {
            const std::string phaseLabel = "PHASE / " + data.phaseText;
            const float phaseWidth = ImGui::CalcTextSize(phaseLabel.c_str()).x;
            const float phasePosition = ImGui::GetContentRegionMax().x - phaseWidth;
            if (ImGui::GetCursorPosX() < phasePosition) {
                ImGui::SameLine(phasePosition);
            }
            ImGui::TextDisabled("%s", phaseLabel.c_str());
        }
    }
    ImGui::EndChild();
    ImGui::Spacing();

    const float footerHeight = logView_.GetPreferredHeight();
    const float mainHeight = std::max(
        0.0f,
        ImGui::GetContentRegionAvail().y - footerHeight - ImGui::GetStyle().ItemSpacing.y
    );
    if (ImGui::BeginChild("PhaseContent", ImVec2(0.0f, mainHeight), true)) {
        switch (data.kind) {
        case PhaseDisplayKind::Loading:
            UIStyle::CenteredMessage("Preparing run", "Waiting for the pipeline to begin.");
            break;
        case PhaseDisplayKind::Processing:
            UIStyle::CenteredMessage("Processing", "The pipeline is preparing the next update.");
            break;
        case PhaseDisplayKind::Progress: {
            const ImVec2 available = ImGui::GetContentRegionAvail();
            const float contentWidth = std::min(available.x, 720.0f);
            ImGui::SetCursorPosY(ImGui::GetCursorPosY() + std::max(24.0f, available.y * 0.28f));
            ImGui::SetCursorPosX(ImGui::GetCursorPosX() + std::max(0.0f, (available.x - contentWidth) * 0.5f));
            ImGui::BeginGroup();
            ImGui::TextDisabled("%s", data.phaseText.empty() ? "PIPELINE PHASE" : data.phaseText.c_str());
            ImGui::SetWindowFontScale(1.12f);
            ImGui::TextUnformatted(data.progressText.empty() ? "Processing..." : data.progressText.c_str());
            ImGui::SetWindowFontScale(1.0f);
            ImGui::Spacing();
            ImGui::ProgressBar(
                std::clamp(data.progress, 0.0f, 1.0f),
                ImVec2(contentWidth, 16.0f)
            );
            ImGui::EndGroup();
            break;
        }
        case PhaseDisplayKind::MaskSelection:
            maskingContent_.Render(data, inputs);
            break;
        case PhaseDisplayKind::Error: {
            const float errorWidth = std::min(ImGui::GetContentRegionAvail().x, 720.0f);
            ImGui::SetCursorPosX(ImGui::GetCursorPosX() +
                std::max(0.0f, (ImGui::GetContentRegionAvail().x - errorWidth) * 0.5f));
            ImGui::PushStyleColor(ImGuiCol_ChildBg, ImVec4(0.20f, 0.07f, 0.08f, 1.0f));
            if (ImGui::BeginChild("ErrorPanel", ImVec2(errorWidth, 110.0f), true)) {
                ImGui::TextColored(ImVec4(0.96f, 0.40f, 0.42f, 1.0f), "PIPELINE ERROR");
                ImGui::Spacing();
                ImGui::TextWrapped("%s", data.errorText.c_str());
            }
            ImGui::EndChild();
            ImGui::PopStyleColor();
            break;
        }
        }
    }
    ImGui::EndChild();
    ImGui::Spacing();
    logView_.Render(data.logs);
    ImGui::End();
}

void PhaseScreen::ResetInteraction() {
    maskingContent_.ResetInteraction();
}

void PhaseScreen::Shutdown() {
    maskingContent_.Shutdown();
}
