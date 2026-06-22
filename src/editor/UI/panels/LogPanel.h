#pragma once

#include "../UIPanel.h"
#include "../../IPCClient.h"

class LogPanel : public UIPanel {
public:
	LogPanel(String name, IPCClient& ipc);
	~LogPanel();

	void Draw() override;
	void PushLog(const String& line);

private:
	void DrawLogLines();

private:
	IPCClient& ipc;
	std::vector<String> logLines;
	char inputPath[512] = "";
	bool scrollToBottom;
};