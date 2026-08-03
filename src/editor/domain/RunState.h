#pragma once

#include "editor/domain/PipelineTypes.h"

#include <filesystem>
#include <optional>
#include <string>

struct RunState {
    RunId id;
    std::string name;
    RunStatus status = RunStatus::Pending;
    PipelinePhase phase = PipelinePhase::Capture;
    std::optional<std::filesystem::path> workspacePath;
    float progress = 0.0f;
    std::string progressLabel;
    std::optional<SelectionRequest> selectionRequest;
    std::optional<std::string> errorMessage;
    std::optional<std::filesystem::path> outputModelPath;
};
