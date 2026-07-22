#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <imgui.h>

class UIPanel;

typedef std::string String;
typedef std::vector<UIPanel*> UIList;
typedef std::unordered_map<String, UIPanel*> UIMap;
