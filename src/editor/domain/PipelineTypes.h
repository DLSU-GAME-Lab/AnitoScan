#pragma once

#include <filesystem>
#include <string>

using RunId = std::string;

struct SelectionRequest {
    std::string frame;
    std::filesystem::path previewPath;
    int candidateCount;
};

enum class RunStatus { Pending, Running, Cancelling, Completed, Failed, Cancelled };
enum class PipelinePhase { Capture, Masking, Spatial, Geometry, Export };
