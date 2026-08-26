#include "editor/ui/screens/RunSetupScreen.h"

#include "editor/ui/UIManager.h"
#include "editor/ui/UIStyle.h"

#include <algorithm>
#include <string>

#include <imgui.h>

void RunSetupScreen::Render(const RunSetupData& data, std::vector<UIInput>& inputs) {
    const ImGuiViewport* mainViewport = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(mainViewport->WorkPos);
    ImGui::SetNextWindowSize(mainViewport->WorkSize);

    constexpr ImGuiWindowFlags windowFlags =
        ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoSavedSettings;
    ImGui::Begin("Run Setup", nullptr, windowFlags);

    if (ImGui::BeginChild("SetupHeader", ImVec2(0.0f, 92.0f), true, ImGuiWindowFlags_NoScrollbar)) {
        ImGui::TextDisabled("ANITOSCAN / RUN SETUP");
        ImGui::SetWindowFontScale(1.18f);
        ImGui::TextUnformatted("Create Reconstruction Run");
        ImGui::SetWindowFontScale(1.0f);
        ImGui::TextDisabled("Configure an input source and reconstruction profile.");
    }
    ImGui::EndChild();
    ImGui::Spacing();

    const float contentWidth = ImGui::GetContentRegionAvail().x;
    ImGui::BeginGroup();

    const float availableHeight = ImGui::GetContentRegionAvail().y;
    const float configurationHeight = std::clamp(availableHeight * 0.60f, 280.0f, 440.0f);
    if (ImGui::BeginChild("ConfigurationPanel", ImVec2(contentWidth, configurationHeight), true)) {
        UIStyle::SectionTitle("RUN CONFIGURATION", "Primary capture and reconstruction settings.");

        if (ImGui::BeginTable("RunConfiguration", 2, ImGuiTableFlags_SizingStretchProp)) {
            ImGui::TableSetupColumn("Label", ImGuiTableColumnFlags_WidthFixed, 150.0f);
            ImGui::TableSetupColumn("Value", ImGuiTableColumnFlags_WidthStretch);

            ImGui::TableNextRow();
            ImGui::TableNextColumn();
            ImGui::TextDisabled("Run name");
            ImGui::TableNextColumn();
            ImGui::SetNextItemWidth(-1.0f);
            ImGui::InputText("##RunName", runName_.data(), runName_.size());

            ImGui::TableNextRow();
            ImGui::TableNextColumn();
            ImGui::TextDisabled("Input source");
            ImGui::TableNextColumn();
            ImGui::SetNextItemWidth(-1.0f);
            ImGui::InputText("##InputSource", inputSource_.data(), inputSource_.size());

            ImGui::TableNextRow();
            ImGui::TableNextColumn();
            ImGui::TextDisabled("Minimum frames");
            ImGui::TableNextColumn();
            ImGui::SetNextItemWidth(-1.0f);
            ImGui::InputInt("##MinimumFrames", &minimumFrames_);
            minimumFrames_ = std::max(1, minimumFrames_);

            ImGui::TableNextRow();
            ImGui::TableNextColumn();
            ImGui::TextDisabled("Quality");
            ImGui::TableNextColumn();
            ImGui::SetNextItemWidth(-1.0f);
            ImGui::Combo("##Quality", &quality_, "Fast\0Medium\0Detailed\0");
            ImGui::EndTable();
        }

        ImGui::Spacing();
        if (ImGui::CollapsingHeader("Advanced settings")) {
            if (ImGui::BeginTable("AdvancedConfiguration", 2, ImGuiTableFlags_SizingStretchProp)) {
                ImGui::TableSetupColumn("Label", ImGuiTableColumnFlags_WidthFixed, 150.0f);
                ImGui::TableSetupColumn("Value", ImGuiTableColumnFlags_WidthStretch);

                ImGui::TableNextRow(); ImGui::TableNextColumn(); ImGui::TextDisabled("Mode");
                ImGui::TableNextColumn(); ImGui::SetNextItemWidth(-1.0f); ImGui::Combo("##Mode", &pipelineMode_, "Disk\0Pipe\0");
                ImGui::TableNextRow(); ImGui::TableNextColumn(); ImGui::TextDisabled("Capture mode");
                ImGui::TableNextColumn(); ImGui::SetNextItemWidth(-1.0f); ImGui::Combo("##CaptureMode", &captureMode_, "Auto\0Image\0Video\0");
                ImGui::TableNextRow(); ImGui::TableNextColumn(); ImGui::TextDisabled("IOU threshold");
                ImGui::TableNextColumn(); ImGui::SetNextItemWidth(-1.0f); ImGui::SliderFloat("##IOUThreshold", &iouThreshold_, 0.0f, 1.0f);
                ImGui::TableNextRow(); ImGui::TableNextColumn(); ImGui::TextDisabled("Drift limit");
                ImGui::TableNextColumn(); ImGui::SetNextItemWidth(-1.0f); ImGui::InputInt("##DriftLimit", &driftLimit_);
                driftLimit_ = std::max(0, driftLimit_);
                ImGui::TableNextRow(); ImGui::TableNextColumn(); ImGui::TextDisabled("YOLO model");
                ImGui::TableNextColumn(); ImGui::SetNextItemWidth(-1.0f); ImGui::Combo("##YoloModel", &modelSize_, "n\0s\0m\0l\0x\0");
                ImGui::TableNextRow(); ImGui::TableNextColumn(); ImGui::TextDisabled("Rebuild cache");
                ImGui::TableNextColumn(); ImGui::Checkbox("Force rebuild", &forceRebuild_);
                ImGui::EndTable();
            }
        }

        ImGui::Spacing();
        const bool validInput = runName_[0] != '\0' && inputSource_[0] != '\0';
        ImGui::BeginDisabled(!data.canCreateRun || !validInput);
        if (UIStyle::Button("Create Run", UIStyle::ButtonKind::Primary)) {
            inputs.push_back({
                UIClick::CreateRun,
                std::string(runName_.data()) + "\n" + inputSource_.data() + "\n" +
                    std::to_string(minimumFrames_) + "\n" + std::to_string(pipelineMode_) + "\n" +
                    std::to_string(captureMode_) + "\n" + std::to_string(quality_) + "\n" +
                    std::to_string(iouThreshold_) + "\n" + std::to_string(driftLimit_) + "\n" +
                    std::to_string(modelSize_) + "\n" + (forceRebuild_ ? "1" : "0")
            });
        }
        ImGui::EndDisabled();
        if (!data.message.empty()) {
            ImGui::SameLine();
            ImGui::TextColored(ImVec4(0.94f, 0.67f, 0.24f, 1.0f), "%s", data.message.c_str());
        }
    }
    ImGui::EndChild();

    ImGui::Spacing();
    if (ImGui::BeginChild("ExistingRunsPanel", ImVec2(contentWidth, 0.0f), true)) {
        runSelector_.Render(data, inputs);
    }
    ImGui::EndChild();
    ImGui::EndGroup();
    ImGui::End();
}
