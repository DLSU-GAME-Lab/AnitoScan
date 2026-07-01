#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <imgui.h>
//#include "UI/UIHelper.h"

class UIPanel;

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

struct BackendMessage {
	String type;
	String raw;
};