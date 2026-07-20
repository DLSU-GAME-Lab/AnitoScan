#include "LogPanel.h"

LogPanel::LogPanel(String name, IPCClient& ipc) 
	: UIPanel(UIType::LOG_PANEL, name), ipc(ipc) {}

LogPanel::~LogPanel() {}

// Main render loop for the log interface and processes actions
void LogPanel::Draw() {
	ImGui::Begin(this->name.c_str());

	ImGui::TextDisabled("Click a line to copy to clipboard");
	if (ImGui::SmallButton("Clear")) {
		this->logLines.clear();
	}

	ImGui::BeginChild("##log", ImVec2(0, 0), true);

	DrawLogLines();

	if (this->scrollToBottom) {
		ImGui::SetScrollHereY(1.0f);
	}
	this->scrollToBottom = false;

	ImGui::EndChild();

	ImGui::End();
}


// Appends a new message entry to the log collection history and trims older log entries once it reaches 500 lines
void LogPanel::PushLog(const String& line) {
	this->logLines.push_back(line);
	this->scrollToBottom = true;

	if (logLines.size() > 500) {
		logLines.erase(logLines.begin());
	}
}

// Handles custom formatting, background hover states, and input event maps for log lines
void LogPanel::DrawLogLines() {
	for (int i = 0; i < this->logLines.size(); i++) {
		String line = this->logLines[i];
		if (line == "") continue;

		//display
		ImVec2 startPos = ImGui::GetCursorScreenPos();
		ImGui::TextWrapped("> %s", line.c_str());
		ImVec2 endPos = ImGui::GetCursorScreenPos();

		ImVec2 minBound = startPos;
		ImVec2 maxBound = ImVec2(startPos.x + ImGui::GetContentRegionAvail().x, endPos.y);

		//clickable
		ImGui::SetCursorScreenPos(startPos);
		String id = "##log_row" + std::to_string(i);
		bool clicked = ImGui::InvisibleButton(id.c_str(), ImVec2(maxBound.x - minBound.x, maxBound.y - minBound.y));
		ImGui::SetCursorScreenPos(endPos);

		//copy to clipboard
		if (clicked) {
			ImGui::SetClipboardText(line.c_str());
		}

		//background hover
		if (ImGui::IsItemHovered()) {
			ImU32 hover_bg = ImGui::ColorConvertFloat4ToU32(ImVec4(1.0f, 1.0f, 1.0f, 0.07f));
			ImGui::GetWindowDrawList()->AddRectFilled(minBound, maxBound, hover_bg);
		}

		//display separator line
		float gap = 4.0f;
		ImVec2 lineStart = ImVec2(startPos.x, endPos.y + gap);
		ImVec2 lineEnd = ImVec2(startPos.x + ImGui::GetContentRegionAvail().x, endPos.y + gap);
		ImU32 color = ImGui::ColorConvertFloat4ToU32(GetUIColor(UIColor::GRAY));
		ImGui::GetWindowDrawList()->AddLine(lineStart, lineEnd, color, 1.0f);

		ImGui::Dummy(ImVec2(0.0f, gap + 4.0f));
	}

}
