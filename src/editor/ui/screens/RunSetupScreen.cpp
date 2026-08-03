#include "editor/ui/screens/RunSetupScreen.h"

#include "editor/controller/PipelineController.h"
#include "editor/domain/EditorState.h"

#include <algorithm>

#include <imgui.h>

void RunSetupScreen::Render(const EditorState& state, PipelineController& controller) {
    const ImGuiViewport* mainViewport = ImGui::GetMainViewport();
    ImGui::SetNextWindowPos(mainViewport->WorkPos);
    ImGui::SetNextWindowSize(mainViewport->WorkSize);

    constexpr ImGuiWindowFlags windowFlags =
        ImGuiWindowFlags_NoDecoration |
        ImGuiWindowFlags_NoMove |
        ImGuiWindowFlags_NoSavedSettings;

    ImGui::Begin("Run Setup", nullptr, windowFlags);
    ImGui::TextUnformatted("Run Setup");
    ImGui::Separator();
    const bool nameChanged = ImGui::InputText("Run name", runName_.data(), runName_.size());
    const bool inputChanged = ImGui::InputText(
        "Input source",
        inputSource_.data(),
        inputSource_.size()
    );
    if (nameChanged || inputChanged) {
        creationError_.clear();
    }

    ImGui::InputInt("Minimum frames", &config_.minimumFrames);
    config_.minimumFrames = std::max(1, config_.minimumFrames);

    int pipelineMode = static_cast<int>(config_.mode);
    if (ImGui::Combo("Mode", &pipelineMode, "Disk\0Pipe\0")) {
        config_.mode = static_cast<PipelineMode>(pipelineMode);
    }

    int captureMode = static_cast<int>(config_.captureMode);
    if (ImGui::Combo("Capture mode", &captureMode, "Auto\0Image\0Video\0")) {
        config_.captureMode = static_cast<CaptureMode>(captureMode);
    }

    int quality = static_cast<int>(config_.quality);
    if (ImGui::Combo("Quality", &quality, "Fast\0Medium\0Detailed\0")) {
        config_.quality = static_cast<Quality>(quality);
    }

    ImGui::SliderFloat("IOU threshold", &config_.iouThreshold, 0.0f, 1.0f);
    ImGui::InputInt("Drift limit", &config_.driftLimit);
    config_.driftLimit = std::max(0, config_.driftLimit);

    constexpr const char* modelSizes[] = {"n", "s", "m", "l", "x"};
    int modelSize = 1;
    for (int index = 0; index < 5; ++index) {
        if (config_.yoloModelSize == modelSizes[index]) {
            modelSize = index;
            break;
        }
    }
    if (ImGui::Combo("YOLO model", &modelSize, "n\0s\0m\0l\0x\0")) {
        config_.yoloModelSize = modelSizes[modelSize];
    }
    ImGui::Checkbox("Force rebuild", &config_.force);

    if (ImGui::Button("Create Run") && runName_[0] != '\0') {
        if (inputSource_[0] == '\0') {
            creationError_ = "Input source is required";
        } else {
            config_.inputSource = inputSource_.data();
            switch (controller.CreateRun(runName_.data(), config_)) {
            case CreateRunResult::Created:
                runName_.fill('\0');
                creationError_.clear();
                break;
            case CreateRunResult::DuplicateName:
                creationError_ = "A run with this name already exists";
                break;
            case CreateRunResult::InvalidName:
                creationError_ = "Run name contains invalid path characters";
                break;
            case CreateRunResult::InvalidConfig:
                creationError_ = "Run settings are invalid";
                break;
            case CreateRunResult::StorageError:
                creationError_ = "Failed to save the run";
                break;
            }
        }
    }
    if (!creationError_.empty()) {
        ImGui::TextColored(
            ImVec4(1.0f, 0.35f, 0.35f, 1.0f),
            "%s",
            creationError_.c_str()
        );
    }

    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Spacing();
    runSelector_.Render(state, controller);
    ImGui::End();
}
