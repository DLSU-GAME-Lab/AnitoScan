#pragma once

#include <filesystem>
#include <map>
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
    std::vector<std::string> outputModelPaths;
    std::string outputModelPath;
    std::map<std::string, std::string> outputPreviewPaths;
};

struct ExportState {
    bool busy = false;
    std::string requestId;
    std::string runId;
    std::string outputPath;
    std::string error;
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
    int imageWidth = 0;
    int imageHeight = 0;
    int selectionId = 0;
    bool selectionSubmitting = false;
    std::string selectionError;
    std::vector<std::string> logs;
    std::string error;
};

enum class PhaseDisplayKind {
    Loading,
    Processing,
    Progress,
    MaskSelection,
    Export,
    Error
};

struct PhaseNavigationData {
    bool viewingLatest = true;
    bool canGoBack = false;
    bool canGoNext = false;
    bool canFollowLive = false;
    bool canStopFollowingLive = false;
};

struct PhaseDisplayData {
    std::string runId;
    std::string runName;
    std::string statusText;
    PhaseDisplayKind kind = PhaseDisplayKind::Loading;
    std::string phaseText;
    std::string progressText;
    std::string previewPath;
    std::string errorText;
    float progress = 0.0f;
    int candidateCount = 0;
    int imageWidth = 0;
    int imageHeight = 0;
    int selectionId = 0;
    bool selectionSubmitting = false;
    std::string selectionError;
    std::vector<std::string> logs;
    PhaseNavigationData navigation;
    bool maskSelectionEnabled = false;
    std::string selectedOutputModelPath;
    std::vector<std::string> exportFormats;
    bool exportAvailable = false;
    ExportState exportState;
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
