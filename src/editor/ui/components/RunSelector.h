#pragma once

#include "editor/ui/UIInput.h"

#include <string>
#include <vector>

struct RunSetupData;

class RunSelector {
public:
    void Render(const RunSetupData& data, std::vector<UIInput>& inputs);

private:
    std::string pendingDeleteRunId_;
    std::string pendingDeleteRunName_;
};
