#include "ScanPanel.h"

ScanPanel::ScanPanel(IPCClient& ipc) : UIPanel(UIType::SCAN_PANEL), ipc(ipc) {
	this->isScanning = false;
	this->scrollToBottom = true;	
	this->progress = 0.0f;
	this->progressLabel = "Idle";
}

ScanPanel::~ScanPanel() {}

void ScanPanel::PushLog(const String& line) {
	this->logLines.push_back(line);
	this->scrollToBottom = true;

	if (logLines.size() > 500) {
		logLines.erase(logLines.begin());
	}
}

void ScanPanel::SetProgress(float value, String& label) {
	this->progress = value;
	this->progressLabel = label;
}

void ScanPanel::SetDone() {
	this->isScanning = false;
	this->progress = 1.0f;
	this->progressLabel = "Complete";
}


void ScanPanel::DrawActions() {
	if (ImGui::Button("Ping")) {
		nlohmann::json cmd;
		cmd["action"] = "ping";
		this->ipc.Send(cmd.dump());
	}

	ImGui::SameLine();

	ImGui::BeginDisabled(this->isScanning);
	if (ImGui::Button("Run Pipeline")) {
		this->isScanning = true;
		this->progress = 0.0f;
		this->progressLabel = "Starting...";
		this->logLines.clear();

		nlohmann::json cmd;
		cmd["action"] = "run_scan";
		cmd["name"] = "test_run";
		cmd["input"] = "IMG_7518.mp4";
		cmd["fps"] = 10;
		this->ipc.Send(cmd.dump());
	}
	ImGui::EndDisabled();

	ImGui::SameLine();

	ImGui::BeginDisabled(!this->isScanning);


	//TODO: implement cancellation option on every phase once pipeline.py is connected
	if (ImGui::Button("Cancel")) {
		this->isScanning = false;
		this->ipc.Shutdown();
		ipc.Start(".venv\\Scripts\\python.exe", "src/pipeline/core/dummy.py");
	}
	ImGui::EndDisabled();

}

void ScanPanel::DrawProgress() {
	if (this->isScanning && this->progress > 0.0f) {
		ImGui::ProgressBar(this->progress, ImVec2(-1, 0));
		ImGui::Text("%.0f%% - %s", this->progress * 100.0f, this->progressLabel.c_str());
	}
}

void ScanPanel::DrawLog() {
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

}

// MAIN DRAW
void ScanPanel::Draw() {
	ImGui::Begin("Scan Panel");

	DrawActions();
	ImGui::Separator();
	DrawProgress();
	ImGui::Separator();
	DrawLog();
	ImGui::Separator();

	ImGui::End();
}
