#include "OverviewPanel.h"

OverviewPanel::OverviewPanel(String name, const EditorState& state, PipelineController* controller)
    : UIPanel(UIType::OVERVIEW, name), state(state), controller(controller) {}

OverviewPanel::~OverviewPanel() {}

void OverviewPanel::SetInput(String input, String output, int minFrames, String quality) {
    this->inputFile = input;
    this->outputFolder = output;
    this->minFrames = minFrames;
    this->quality = quality;
    this->inputReady = true;
}

void OverviewPanel::DrawInputSection() {
    InputWindow* input = static_cast<InputWindow*>(UIManager::GetInstance()->GetPanelByType(UIType::INPUT));

    // Determine if the pipeline is actively running based on EditorState
    bool isScanning = (state.pipeline.runState == RunState::STARTING ||
                       state.pipeline.runState == RunState::RUNNING ||
                       state.pipeline.runState == RunState::AWAITING_ACTION);

    if (!isScanning && !this->inputReady) {
        if (ImGui::Button("Open Input Window"))
            input->ShowWindow();
        return;
    }

    if (isScanning) {
        ImGui::SeparatorText("Current Input");
    }
    else {
        if (ImGui::Button("Modify Input"))
            input->ShowWindow();
    }

    ImGui::Spacing();
    ImGui::Text("Selected: ");
    ImGui::SameLine();
    std::filesystem::path path(this->inputFile);
    HighlightImGuiText(path.filename().string(), UIColor::GREEN);

    ImGui::Text("Output folder: ");
    ImGui::SameLine();
    HighlightImGuiText(this->outputFolder, UIColor::GREEN);

    ImGui::Text("Minimum Frames: ");
    ImGui::SameLine();
    HighlightImGuiText(std::to_string(this->minFrames), UIColor::GREEN);

    ImGui::Text("Quality: ");
    ImGui::SameLine();
    HighlightImGuiText(this->quality, UIColor::GREEN);
    ImGui::Spacing();
}

void OverviewPanel::DrawActions() {
    bool isRunning = (state.pipeline.runState == RunState::STARTING ||
                      state.pipeline.runState == RunState::RUNNING ||
                      state.pipeline.runState == RunState::AWAITING_ACTION);

    ImGui::BeginDisabled(isRunning || !this->inputReady);
    if (ImGui::Button("Run Pipeline") && controller) {
        controller->StartRun(this->outputFolder, this->inputFile, this->minFrames, this->quality);
    }
    ImGui::EndDisabled();
    ImGui::SameLine();

    ImGui::BeginDisabled(!isRunning);
    if (ImGui::Button("Cancel Scan") && controller) {
        controller->CancelRun();
    }
    ImGui::EndDisabled();
    ImGui::Spacing();
}

void OverviewPanel::DrawOverallProgress() {
    ImGui::SeparatorText("Overall Progress");
    ImGui::ProgressBar(state.pipeline.overallProgress, ImVec2(-1, 20));
}

void OverviewPanel::DrawPhaseBreakdown() {
    const char* phaseNames[]{ "", "Phase 1: Capture", "Phase 2: Masking", "Phase 3: Spatial", "Phase 4: Geometry", "Phase 5: Export" };
    int activePhaseIdx = static_cast<int>(state.pipeline.activePhase);

    for (int i = 1; i <= 5; i++) {
        ImGui::PushID(i);

        bool isCompleted = (state.pipeline.runState == RunState::COMPLETED) || (activePhaseIdx > i && activePhaseIdx != 0);
        bool isActive = (activePhaseIdx == i && state.pipeline.runState != RunState::COMPLETED);

        UIColor barColor = UIColor::NONE;
        float progressValue = 0.0f;
        String label = "Waiting...";

        if (isCompleted) {
            HighlightImGuiText(String("[DONE] ") + phaseNames[i], UIColor::GREEN);
            barColor = UIColor::GREEN;
            progressValue = 1.0f;
            label = "Complete";
        } else if (isActive) {
            HighlightImGuiText(String("[ >> ] ") + phaseNames[i], UIColor::YELLOW);
            barColor = UIColor::YELLOW;
            progressValue = state.pipeline.phaseProgress;
            label = state.pipeline.progressLabel.empty() ? "In Progress" : state.pipeline.progressLabel;
        } else {
            ImGui::TextDisabled("[    ] %s", phaseNames[i]);
        }

        UpdateImGuiProgressBar(progressValue, ImVec2(-1, 12), barColor);

        if (isActive || isCompleted) {
            ImGui::TextDisabled("  %s", label.c_str());
        }

        ImGui::Spacing();
        ImGui::PopID();
    }
}

void OverviewPanel::Draw() {
    ImGui::Begin(this->name.c_str());
    DrawActions();
    ImGui::Separator();

    DrawInputSection();

    if (state.pipeline.runState != RunState::IDLE) {
        DrawOverallProgress();
        DrawPhaseBreakdown();
    }
    ImGui::End();
}
