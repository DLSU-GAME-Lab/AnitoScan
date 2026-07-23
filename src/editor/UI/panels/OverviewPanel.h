#pragma once
#include "../UIPanel.h"
#include "../UIManager.h"
#include "../../state/EditorState.h"
#include "../../controller/PipelineController.h"

class OverviewPanel : public UIPanel {
public:
    OverviewPanel(String name, const EditorState& state, PipelineController* controller);
    ~OverviewPanel();

    void Draw() override;
    void SetInput(String input, String output, int minFrames, String quality);

private:
    void DrawInputSection();
    void DrawActions();
    void DrawOverallProgress();
    void DrawPhaseBreakdown();

private:
    const EditorState& state;
    PipelineController* controller;

    // Kept strictly for local Input Window configuration drafting
    String inputFile, outputFolder, quality;
    int minFrames = 0;
    bool inputReady = false;
};
