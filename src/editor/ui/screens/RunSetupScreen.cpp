#include "editor/ui/screens/RunSetupScreen.h"

#include "editor/ui/UIManager.h"

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
    ImGui::TextUnformatted("Run Setup");
    ImGui::Separator();

    ImGui::InputText("Run name", runName_.data(), runName_.size());
    ImGui::InputText("Input source", inputSource_.data(), inputSource_.size());
    ImGui::InputInt("Minimum frames", &minimumFrames_);
    minimumFrames_ = std::max(1, minimumFrames_);
    ImGui::Combo("Mode", &pipelineMode_, "Disk\0Pipe\0");
    ImGui::Combo("Capture mode", &captureMode_, "Auto\0Image\0Video\0");
    ImGui::Combo("Quality", &quality_, "Fast\0Medium\0Detailed\0");
    ImGui::SliderFloat("IOU threshold", &iouThreshold_, 0.0f, 1.0f);
    ImGui::InputInt("Drift limit", &driftLimit_);
    driftLimit_ = std::max(0, driftLimit_);
    ImGui::Combo("YOLO model", &modelSize_, "n\0s\0m\0l\0x\0");
    ImGui::Checkbox("Force rebuild", &forceRebuild_);

    ImGui::BeginDisabled(!data.canCreateRun);
    if (ImGui::Button("Create Run") && runName_[0] != '\0' && inputSource_[0] != '\0') {
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
        ImGui::TextWrapped("%s", data.message.c_str());
    }

    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Spacing();
    runSelector_.Render(data, inputs);
    ImGui::End();
}
