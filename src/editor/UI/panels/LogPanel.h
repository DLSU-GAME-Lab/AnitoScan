#pragma once
#include "../UIPanel.h"
#include "../../state/EditorState.h"
#include <vector>

class LogPanel : public UIPanel {
public:
    LogPanel(String name, EditorState& state);
    ~LogPanel();

    void Draw() override;
    void PushLog(const String& line);

private:
    void DrawLogLines();

private:
    EditorState& state;
    std::vector<String> logLines;
    bool scrollToBottom = false;
};
