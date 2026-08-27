#include "editor/ui/screens/PostExportScreen.h"

#include "editor/ui/UIManager.h"
#include "editor/ui/UIStyle.h"

#include <imgui.h>

#include <filesystem>
#include <string>

namespace {
std::string ModelLabel(const std::string& path, const std::string& runName) {
    const std::filesystem::path modelPath(path);
    const std::string stem = modelPath.stem().string();
    if (stem == runName + "_fast") return "Fast";
    if (stem == runName + "_medium") return "Medium";
    if (stem == runName + "_detailed") return "Detailed";
    return modelPath.filename().string();
}
}

void PostExportScreen::Render(const PostExportData& data, std::vector<UIInput>& inputs) {
    const ImGuiViewport* mainViewport = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(mainViewport->WorkPos);
    ImGui::SetNextWindowSize(mainViewport->WorkSize);

    constexpr ImGuiWindowFlags windowFlags =
        ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoSavedSettings;
    ImGui::Begin("Post Export", nullptr, windowFlags);
    if (ImGui::BeginChild("PostExportHeader", ImVec2(0.0f, 92.0f), true, ImGuiWindowFlags_NoScrollbar)) {
        if (ImGui::BeginTable("Header", 2, ImGuiTableFlags_SizingStretchProp)) {
            ImGui::TableSetupColumn("Run", ImGuiTableColumnFlags_WidthStretch);
            ImGui::TableSetupColumn("Actions", ImGuiTableColumnFlags_WidthFixed);
            ImGui::TableNextColumn();
            ImGui::TextDisabled("ANITOSCAN / POST EXPORT");
            ImGui::SetWindowFontScale(1.18f);
            ImGui::TextUnformatted(data.runName.c_str());
            ImGui::SetWindowFontScale(1.0f);
            ImGui::SameLine();
            UIStyle::StatusBadge(data.statusText);
            ImGui::TableNextColumn();
            ImGui::Dummy(ImVec2(0.0f, 10.0f));
            if (UIStyle::Button("New Run", UIStyle::ButtonKind::Primary)) {
                inputs.push_back({UIClick::NewRun, {}});
            }
            ImGui::SameLine();
            if (UIStyle::Button("Recenter", UIStyle::ButtonKind::Secondary)) {
                recenterRequested_ = true;
            }
            ImGui::EndTable();
        }
    }
    ImGui::EndChild();
    ImGui::Spacing();

    if (ImGui::BeginChild("PostExportToolbar", ImVec2(0.0f, 60.0f), true, ImGuiWindowFlags_NoScrollbar)) {
        ImGui::BeginDisabled(!data.navigation.canGoBack);
        if (UIStyle::Button("Back", UIStyle::ButtonKind::Secondary)) {
            inputs.push_back({UIClick::PreviousPhase, {}});
        }
        ImGui::EndDisabled();

        for (const std::string& modelPath : data.outputModelPaths) {
            ImGui::SameLine();
            const std::string label = ModelLabel(modelPath, data.runName);
            const std::string buttonId = label + "##" + modelPath;
            const UIStyle::ButtonKind kind = modelPath == data.selectedOutputModelPath
                ? UIStyle::ButtonKind::Primary
                : UIStyle::ButtonKind::Secondary;
            if (UIStyle::Button(buttonId.c_str(), kind)) {
                inputs.push_back({UIClick::SelectOutputModel, modelPath});
            }
        }
    }
    ImGui::EndChild();
    ImGui::Spacing();
    viewport_.Render(data.textureId);
    ImGui::End();
}

int PostExportScreen::GetViewportWidth() const {
    return viewport_.GetWidth();
}

int PostExportScreen::GetViewportHeight() const {
    return viewport_.GetHeight();
}

bool PostExportScreen::IsViewportHovered() const {
    return viewport_.IsHovered();
}

bool PostExportScreen::ConsumeRecenterRequest() {
    const bool requested = recenterRequested_;
    recenterRequested_ = false;
    return requested;
}
