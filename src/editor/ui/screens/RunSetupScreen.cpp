#include "editor/ui/screens/RunSetupScreen.h"

#include "editor/ui/UIManager.h"
#include "editor/ui/UIStyle.h"

#include <algorithm>
#include <cctype>

#include <string>

#include <imgui.h>

namespace {
enum class InputSourceIcon { Refresh, Folder };

bool InputSourceButton(const char* id, InputSourceIcon icon, float size) {
    const bool clicked = ImGui::Button(id, ImVec2(size, size));
    const ImVec2 origin = ImGui::GetItemRectMin();
    ImDrawList* drawList = ImGui::GetWindowDrawList();
    const auto point = [&](float x, float y) {
        return ImVec2(origin.x + x * size, origin.y + y * size);
    };
    const ImU32 foreground = ImGui::GetColorU32(ImGuiCol_Text);
    if (icon == InputSourceIcon::Folder) {
        const ImU32 folderColor = ImGui::GetColorU32(ImVec4(0.96f, 0.73f, 0.28f, 1.0f));
        drawList->AddRectFilled(point(0.20f, 0.27f), point(0.48f, 0.43f), folderColor, size * 0.04f);
        drawList->AddRectFilled(point(0.20f, 0.36f), point(0.80f, 0.73f), folderColor, size * 0.04f);
        drawList->AddLine(point(0.25f, 0.44f), point(0.75f, 0.44f),
            ImGui::GetColorU32(ImVec4(0.65f, 0.43f, 0.12f, 1.0f)), 1.0f);
    } else {
        drawList->PathArcTo(point(0.50f, 0.50f), size * 0.25f, 0.65f, 5.60f, 24);
        drawList->PathStroke(foreground, 0, std::max(1.5f, size * 0.06f));
        drawList->AddTriangleFilled(point(0.78f, 0.40f), point(0.57f, 0.37f),
            point(0.73f, 0.21f), foreground);
    }
    return clicked;
}
} // namespace

void RunSetupScreen::Render(const RunSetupData& data, std::vector<UIInput>& inputs) {
    if (std::find(data.inputSources.begin(), data.inputSources.end(), inputSource_) == data.inputSources.end()) {
        inputSource_.clear();
    }
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
            const float buttonSize = ImGui::GetFrameHeight();
            const float spacing = ImGui::GetStyle().ItemInnerSpacing.x;
            ImGui::PushItemWidth(-1.0f);
            const float rowWidth = ImGui::CalcItemWidth();
            ImGui::PopItemWidth();
            const float comboWidth = std::max(1.0f,
                rowWidth - 2.0f * (buttonSize + spacing));
            ImGui::SetNextItemWidth(comboWidth);
            const float popupHeight = ImGui::GetFrameHeightWithSpacing() +
                6.0f * ImGui::GetTextLineHeightWithSpacing() +
                2.0f * ImGui::GetStyle().WindowPadding.y + ImGui::GetStyle().ItemSpacing.y;
            ImGui::SetNextWindowSizeConstraints(ImVec2(comboWidth, 0.0f), ImVec2(comboWidth, popupHeight));
            if (ImGui::BeginCombo("##InputSource", inputSource_.empty() ? "Select input source..." : inputSource_.c_str())) {
                if (ImGui::IsWindowAppearing()) {
                    inputSourceFilter_.fill('\0');
                    ImGui::SetKeyboardFocusHere();
                }
                ImGui::SetNextItemWidth(-1.0f);
                ImGui::InputTextWithHint("##InputSourceFilter", "Type to filter...", inputSourceFilter_.data(), inputSourceFilter_.size());
                ImGui::Separator();
                bool hasMatches = false;
                for (const auto& source : data.inputSources) {
                    const std::string filter = inputSourceFilter_.data();
                    if (std::search(source.begin(), source.end(), filter.begin(), filter.end(),
                        [](unsigned char left, unsigned char right) {
                            return std::tolower(left) == std::tolower(right);
                        }) == source.end() && !filter.empty()) {
                        continue;
                    }
                    hasMatches = true;
                    ImGui::PushID(source.c_str());
                    // Render filenames separately so ImGui's '##' label syntax cannot hide part of a name.
                    if (ImGui::Selectable("##Source", source == inputSource_)) {
                        inputSource_ = source;
                    }
                    ImGui::GetWindowDrawList()->AddText(ImGui::GetItemRectMin(),
                        ImGui::GetColorU32(ImGuiCol_Text), source.c_str());
                    ImGui::PopID();
                }
                if (!hasMatches) {
                    ImGui::TextDisabled(data.inputSources.empty() ? "No files or folders in data/input" : "No matching input sources");
                }
                ImGui::EndCombo();
            }
            ImGui::SameLine(0.0f, spacing);

            if (InputSourceButton("##RefreshInputs", InputSourceIcon::Refresh, buttonSize)) {
                inputs.push_back({UIClick::RefreshInputSources, {}});
            }
            if (ImGui::IsItemHovered()) ImGui::SetTooltip("Refresh input sources (rescan data/input)");
            ImGui::SameLine(0.0f, spacing);

            if (InputSourceButton("##OpenInputDirectory", InputSourceIcon::Folder, buttonSize)) {
                inputs.push_back({UIClick::OpenInputDirectory, {}});
            }
            if (ImGui::IsItemHovered()) ImGui::SetTooltip("Open data/input to add files or image folders, then refresh");
            if (!data.inputSourceListError.empty()) {
                ImGui::TextWrapped("%s", data.inputSourceListError.c_str());
            }

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
        const bool validInput = runName_[0] != '\0' && !inputSource_.empty();
        const bool duplicateName = std::find(data.runNames.begin(), data.runNames.end(), runName_.data()) != data.runNames.end();
        ImGui::BeginDisabled(!data.canCreateRun || !validInput || duplicateName);
        if (UIStyle::Button("Create Run", UIStyle::ButtonKind::Primary)) {
            inputs.push_back({
                UIClick::CreateRun,
                std::string(runName_.data()) + "\n" + inputSource_ + "\n" +
                    std::to_string(minimumFrames_) + "\n" + std::to_string(pipelineMode_) + "\n" +
                    std::to_string(captureMode_) + "\n" + std::to_string(quality_) + "\n" +
                    std::to_string(iouThreshold_) + "\n" + std::to_string(driftLimit_) + "\n" +
                    std::to_string(modelSize_) + "\n" + (forceRebuild_ ? "1" : "0")
            });
        }
        ImGui::EndDisabled();
        std::string message = data.message;
        if (message.empty() && duplicateName) {
            message = "Run already exists";
        }
        if (message.empty() && data.rejectedInputSource == inputSource_) {
            message = data.inputError;
        }
        if (!message.empty()) {
            ImGui::SameLine();
            ImGui::TextColored(ImVec4(0.94f, 0.67f, 0.24f, 1.0f), "%s", message.c_str());
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
