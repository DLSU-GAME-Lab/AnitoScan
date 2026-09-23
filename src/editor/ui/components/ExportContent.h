#pragma once

#include <array>
#include <string>
#include <vector>

struct PhaseDisplayData;
struct UIInput;

class ExportContent {
public:
    void Render(const PhaseDisplayData& data, std::vector<UIInput>& inputs);

private:
    bool exportSettingsInitialized_ = false;
    bool destinationInitialized_ = false;
    std::string exportRunId_;
    std::string exportFormat_ = "obj";
    std::string autoAssetName_;
    std::array<char, 4096> destination_{};
    std::array<char, 1024> assetName_{};
};
