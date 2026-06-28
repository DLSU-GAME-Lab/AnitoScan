#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <imgui.h>

class UIPanel;

enum class UIType {
	MENU_BAR,
	OVERVIEW,
	DOCKSPACE,
	FILE_VIEWER,
	LOG_PANEL,
	MASKING_MODAL,
	VIEWPORT,
	UNKNOWN
};

enum class Phase {
	NONE = -1,
	CAPTURE = 0,
	MASKING = 1,
	SPATIAL = 2,
	GEOMETRY = 3,
	EXPORT = 4,
	COUNT = 5
};


typedef std::string String;
typedef std::vector<UIPanel*> UIList;
typedef std::unordered_map<String, UIPanel*> UIMap;
//typedef std::unordered_map<UIColor, ImVec4> UIColorMap;
//
//inline const UIColorMap Color = {
//	{ UIColor::NONE,   ImVec4(0.0f, 0.0f, 0.0f, 0.0f) },
//	{ UIColor::YELLOW, ImVec4(1.0f, 1.0f, 0.0f, 1.0f) },
//	{ UIColor::RED,    ImVec4(1.0f, 0.0f, 0.0f, 1.0f) },
//	{ UIColor::BLUE,   ImVec4(0.0f, 0.0f, 1.0f, 1.0f) },
//	{ UIColor::GREEN,  ImVec4(0.0f, 1.0f, 0.0f, 1.0f) }
//};

struct BackendMessage {
	String type;
	String raw;
};