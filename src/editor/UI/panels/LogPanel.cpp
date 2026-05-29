#include "LogPanel.h"

LogPanel::LogPanel(String name, IPCClient& ipc) : UIPanel(UIType::LOG_PANEL, name), ipc(ipc) {

}

LogPanel::~LogPanel() {}

void LogPanel::Draw() {
	ImGui::Begin(this->name.c_str());

	ImGui::Text("Log:");
	ImGui::SameLine();
	if (ImGui::SmallButton("Clear")) {
		this->logLines.clear();
	}

	ImGui::BeginChild("##log", ImVec2(0, 0), true);
	for (String line : this->logLines) {
		ImGui::TextUnformatted(line.c_str());
	}

	if (this->scrollToBottom) {
		ImGui::SetScrollHereY(1.0f);
	}
	this->scrollToBottom = false;

	ImGui::EndChild();

	ImGui::End();
}

void LogPanel::PushLog(const String& line) {
	this->logLines.push_back(line);
	this->scrollToBottom = true;

	if (logLines.size() > 500) {
		logLines.erase(logLines.begin());
	}
}
