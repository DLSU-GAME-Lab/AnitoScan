#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <imgui.h>

class UIPanel;

enum class Phase {
	NONE = 0,
	CAPTURE = 1,
	MASKING = 2,
	SPATIAL = 3,
	GEOMETRY = 4,
	EXPORT = 5,
	COUNT = 6
};

typedef std::string String;
typedef std::vector<UIPanel*> UIList;
typedef std::unordered_map<String, UIPanel*> UIMap;
