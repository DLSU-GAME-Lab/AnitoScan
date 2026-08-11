#pragma once


#include <filesystem>
#include <vector>

struct StoredRun {
    std::string id;
    std::string name;
    std::string status;
    std::filesystem::path inputSource;
    std::string mode;
    std::string captureMode;
    std::string quality;
    bool force = false;
    float iouThreshold = 0.5f;
    int minimumFrames = 45;
    int driftLimit = 200;
    std::string yoloModelSize;
    std::string outputModelPath;
};

class RunStore {
public:
    explicit RunStore(std::filesystem::path runsDirectory);

    std::vector<StoredRun> LoadRuns() const;

    bool LoadRun(
        const std::string& runId,
        StoredRun& run
    ) const;

    bool SaveRun(const StoredRun& run) const;
    bool DeleteRun(const std::string& runId) const;

private:
    std::filesystem::path runsDirectory_;
};
