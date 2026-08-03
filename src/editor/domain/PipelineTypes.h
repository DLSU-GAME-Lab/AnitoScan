#pragma once

#include <filesystem>
#include <string>

using RunId = std::string;

enum class CaptureMode { Auto, Image, Video };
enum class PipelineMode { Disk, Pipe };
enum class Quality { Fast, Medium, Detailed };

struct RunConfig {
    std::filesystem::path inputSource;
    int minimumFrames = 45;
    PipelineMode mode = PipelineMode::Disk;
    CaptureMode captureMode = CaptureMode::Auto;
    Quality quality = Quality::Fast;
    bool force = false;
    float iouThreshold = 0.5f;
    int driftLimit = 200;
    std::string yoloModelSize = "s";
};

struct SelectionRequest {
    std::string frame;
    std::filesystem::path previewPath;
    int candidateCount;
};

enum class RunStatus { Pending, Running, Cancelling, Completed, Failed, Cancelled };
enum class PipelinePhase { Capture, Masking, Spatial, Geometry, Export };
