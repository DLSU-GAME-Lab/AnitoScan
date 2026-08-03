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
    std::optional<std::filesystem::path> outputModelPath;
};
