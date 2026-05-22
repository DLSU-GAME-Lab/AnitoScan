#pragma once

#include <string>
#include <vector>
#include <unordered_map>

class UIPanel;

enum class UIType {
	MENU_BAR,
	DOCKSPACE,
	SCAN_PANEL,
	CAPTURE_PANEL,
	UNKNOWN
};

typedef std::string String;
typedef std::vector<UIPanel*> UIList;
typedef std::unordered_map<UIType, UIPanel*> UIMap;

struct BackendMessage {
	String type;
	String raw;
};