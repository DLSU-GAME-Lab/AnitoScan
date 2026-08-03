#pragma once

#include <filesystem>
#include <string>
#include <vector>

struct BackendConfig {
    std::filesystem::path executable;
    std::vector<std::string> arguments;
    std::filesystem::path workingDirectory;
    std::filesystem::path runsDirectory;
};
