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
    ImGui::TextUnformatted("Pipeline");
    ImGui::Separator();
    ImGui::Text("Run: %s", data.runName.c_str());
    ImGui::Text("Status: %s", data.statusText.c_str());
    ImGui::Text("Phase: %s", data.phaseText.c_str());

    const bool terminal = data.statusText == "failed" || data.statusText == "cancelled";
    if (!terminal && !data.progressText.empty()) {
        ImGui::TextUnformatted(data.progressText.c_str());
        ImGui::ProgressBar(std::clamp(data.progress, 0.0f, 1.0f));
    }
    if (!terminal) {
        maskingContent_.Render(data.previewPath, data.candidateCount, inputs);
    }
    if (!data.errorText.empty()) {
        ImGui::TextColored(ImVec4(1.0f, 0.35f, 0.35f, 1.0f), "%s", data.errorText.c_str());
    }
    ImGui::Separator();
    logView_.Render(data.logs);
    ImGui::Separator();
    runControls_.Render(data.runId, data.statusText, inputs);
    ImGui::End();
}

void PhaseScreen::Shutdown() {
    maskingContent_.Shutdown();
}
