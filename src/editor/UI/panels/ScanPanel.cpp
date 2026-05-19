#include "ScanPanel.h"

ScanPanel::ScanPanel() : UIPanel(UIType::SCAN_PANEL) {}

ScanPanel::~ScanPanel() {}

void ScanPanel::Draw() {
	
	ImGui::Text("test");
	ImGui::ShowDemoWindow();
}