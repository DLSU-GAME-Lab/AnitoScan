#include "editor/ui/screens/PostExportScreen.h"

#include "editor/ui/UIManager.h"
#include "editor/ui/UIStyle.h"

#include <imgui.h>

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
