#pragma once

#include <filesystem>
#include <string>
#include <vector>

struct RunConfig {
    std::filesystem::path inputSource;
    int minimumFrames = 45;
    std::string mode = "disk";
    std::string captureMode = "auto";
    std::string quality = "fast";
    bool force = false;
    float iouThreshold = 0.5f;
    int driftLimit = 200;
    std::string yoloModelSize = "s";
};

struct RunState {
    std::string id;
    std::string name;
    RunConfig config;
    std::string status;
    std::string outputModelPath;
};

struct RunSummary {
    std::string id;
    std::string name;
    std::string status;
};

struct PhaseData {
    std::string phaseName;
    std::string progressText;
    float progress = 0.0f;
    std::string previewPath;
    int candidateCount = 0;
    std::vector<std::string> logs;
    std::string error;
};

struct BackendInput {
    std::string type;
    std::string value;
};

struct PipelineMessage {
    std::string type;
    std::string value;
};

struct PersistenceRequest {
    std::string type;
    std::string runId;
};
