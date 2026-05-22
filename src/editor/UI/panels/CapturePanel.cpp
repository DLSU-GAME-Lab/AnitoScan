#include "CapturePanel.h"

CapturePanel::CapturePanel() : UIPanel(UIType::CAPTURE_PANEL){}


CapturePanel::~CapturePanel() {}


void CapturePanel::Draw() {
	ImGui::Begin("Capture");
	ImGui::Text("Hello World!");

	ImGui::End();
}
