#pragma once

#include "../Types.h"

inline void HighlightImGuiText(String text, UIColor colorCode) {
	ImGui::PushStyleColor(ImGuiCol_Text, Color.at(colorCode));
	ImGui::Text(text.c_str());
	ImGui::PopStyleColor();
}

inline void RightAlignElement(const char* text) {
	float width = ImGui::CalcTextSize(text).x + ImGui::GetStyle().FramePadding.x;
	ImGui::SameLine();
	ImGui::SetCursorPosX(ImGui::GetWindowWidth() - width - ImGui::GetStyle().WindowPadding.x);
}

inline void UpdateImGuiProgressBar(float value, ImVec2 barSize, UIColor colorCode) {
	ImGui::PushStyleColor(ImGuiCol_PlotHistogram, Color.at(colorCode));
	ImGui::ProgressBar(value, barSize);
	ImGui::PopStyleColor();
}