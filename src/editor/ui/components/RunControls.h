#pragma once

#include "editor/ui/UIInput.h"

#include <string>
#include <vector>

class RunControls {
public:
    void Render(const std::string& runId, const std::string& statusText, std::vector<UIInput>& inputs);
};
