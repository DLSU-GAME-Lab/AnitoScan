#include "editor/ui/screens/PostExportScreen.h"

#include "editor/ui/UIManager.h"

#include <imgui.h>

void PostExportScreen::Render(const PostExportData& data, std::vector<UIInput>& inputs) {
    const ImGuiViewport* mainViewport = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(mainViewport->WorkPos);
    ImGui::SetNextWindowSize(mainViewport->WorkSize);

    constexpr ImGuiWindowFlags windowFlags =
        ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoSavedSettings;
    ImGui::Begin("Post Export", nullptr, windowFlags);
    if (ImGui::BeginTable("Header", 2, ImGuiTableFlags_SizingStretchProp)) {
        ImGui::TableSetupColumn("Run", ImGuiTableColumnFlags_WidthStretch);
        ImGui::TableSetupColumn("Actions", ImGuiTableColumnFlags_WidthFixed);
        ImGui::TableNextColumn();
        ImGui::TextUnformatted(data.runName.c_str());
        ImGui::TextDisabled("%s", data.statusText.c_str());
        ImGui::TableNextColumn();
        if (ImGui::Button("New Run")) {
            inputs.push_back({UIClick::NewRun, {}});
        }
        ImGui::SameLine();
        if (ImGui::Button("Recenter")) {
            recenterRequested_ = true;
        }
        ImGui::EndTable();
    }

    ImGui::Separator();
    ImGui::BeginDisabled(!data.navigation.canGoBack);
    if (ImGui::Button("Back")) {
        inputs.push_back({UIClick::PreviousPhase, {}});
    }
    ImGui::EndDisabled();
    ImGui::Separator();
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
