#pragma once

#include "../Types.h"

enum class UIType {
	MENU_TOOLBAR,
	OVERVIEW,
	DOCKSPACE,
	FILE_VIEWER_CAPTURE,
	FILE_VIEWER_MASKING,
	LOG_PANEL,
	MASKING_MODAL,
	VIEWPORT,
	INPUT,
	UNKNOWN
};

enum class UILayout {
	DEFAULT,
	MODEL_VIEWER
};

enum class UIColor {
	NONE,
	YELLOW,
	RED,
	BLUE,
	GREEN,
	GRAY
};


inline ImVec4 GetUIColor(UIColor color) {
	switch (color) {
	case UIColor::NONE:   return ImVec4(0, 0, 0, 0);
	case UIColor::YELLOW: return ImVec4(1, 1, 0, 1);
	case UIColor::RED:    return ImVec4(1, 0, 0, 1);
	case UIColor::BLUE:   return ImVec4(0, 0, 1, 1);
	case UIColor::GREEN:  return ImVec4(0, 1, 0, 1);
	case UIColor::GRAY:	  return ImVec4(0.2, 0.2, 0.2, 1);
	default: return ImVec4(1, 1, 1, 1);
	}
}

inline void HighlightImGuiText(String text, UIColor colorCode) {
	ImGui::PushStyleColor(ImGuiCol_Text, GetUIColor(colorCode));
	ImGui::Text("%s", text.c_str());
	ImGui::PopStyleColor();
}

inline void RightAlignElement(const char* text) {
	float width = ImGui::CalcTextSize(text).x + ImGui::GetStyle().FramePadding.x;
	ImGui::SameLine();
	ImGui::SetCursorPosX(ImGui::GetWindowWidth() - width - ImGui::GetStyle().WindowPadding.x);
}

inline void UpdateImGuiProgressBar(float value, ImVec2 barSize, UIColor colorCode) {
	ImGui::PushStyleColor(ImGuiCol_PlotHistogram, GetUIColor(colorCode));
	ImGui::ProgressBar(value, barSize);
	ImGui::PopStyleColor();
}
