#include "editor/persistence/RunStore.h"

#include <algorithm>
#include <fstream>
#include <nlohmann/json.hpp>

namespace {
using Json = nlohmann::json;

std::filesystem::path FindManifest(const std::filesystem::path& root, const std::string& runId) {
    std::error_code error;
    for (std::filesystem::recursive_directory_iterator it(root, error), end; !error && it != end; it.increment(error)) {
        if (it->path().filename() != "manifest.json") continue;
        std::ifstream input(it->path());
        Json manifest;
        if (input >> manifest && manifest.value("run_id", "") == runId) return it->path();
    }
    return {};
}

StoredRun ReadRun(const std::filesystem::path& manifestPath) {
    std::ifstream input(manifestPath);
    Json manifest;
    input >> manifest;
    StoredRun run;
    run.id = manifest.value("run_id", manifestPath.parent_path().filename().string());
    run.name = manifest.value("run_name", run.id);
    run.status = manifest["status"].value("state", "failed");
    run.outputModelPath = manifest.value("paths", Json::object()).value("output_model", "");
    run.inputSource = manifest.value("input_source", "");
    run.mode = manifest.value("mode", "disk");
    const Json settings = manifest.value("settings", Json::object());
    run.minimumFrames = settings.value("minimum_frames", 45);
    run.captureMode = settings.value("capture_mode", "auto");
    run.quality = settings.value("quality", "fast");
    run.force = settings.value("force", false);
    run.iouThreshold = settings.value("iou_threshold", 0.5f);
    run.driftLimit = settings.value("drift_limit", 200);
    run.yoloModelSize = settings.value("yoloe_model_size", "s");
    return run;
}
}

RunStore::RunStore(std::filesystem::path runsDirectory) : runsDirectory_(std::move(runsDirectory)) {}

std::vector<StoredRun> RunStore::LoadRuns() const {
    std::vector<StoredRun> runs;
    std::error_code error;
    for (std::filesystem::recursive_directory_iterator it(runsDirectory_, error), end; !error && it != end; it.increment(error)) {
        if (it->path().filename() != "manifest.json") continue;
        try { runs.push_back(ReadRun(it->path())); } catch (...) {}
    }
    std::sort(runs.begin(), runs.end(), [](const StoredRun& left, const StoredRun& right) { return left.name < right.name; });
    return runs;
}

bool RunStore::LoadRun(const std::string& runId, StoredRun& run) const {
    const std::filesystem::path manifestPath = FindManifest(runsDirectory_, runId);
    if (manifestPath.empty()) return false;
    try { run = ReadRun(manifestPath); return true; } catch (...) { return false; }
}

bool RunStore::SaveRun(const StoredRun& run) const {
    const std::filesystem::path workspace = runsDirectory_ / run.name;
    std::error_code error;
    std::filesystem::create_directories(workspace, error);
    if (error) return false;
    const Json manifest = {
        {"run_id", run.id}, {"run_name", run.name}, {"input_source", run.inputSource.string()}, {"mode", run.mode},
        {"settings", {{"minimum_frames", run.minimumFrames}, {"capture_mode", run.captureMode}, {"quality", run.quality}, {"force", run.force}, {"iou_threshold", run.iouThreshold}, {"drift_limit", run.driftLimit}, {"yoloe_model_size", run.yoloModelSize}}},
        {"status", {{"state", run.status}, {"phase", 0}, {"completed", Json::array()}}},
        {"paths", {{"run_root", workspace.string()}, {"output_model", run.outputModelPath}}}
    };
    std::ofstream output(workspace / "manifest.json");
    output << manifest.dump(4);
    return static_cast<bool>(output);
}

bool RunStore::DeleteRun(const std::string& runId) const {
    const std::filesystem::path manifestPath = FindManifest(runsDirectory_, runId);
    if (manifestPath.empty()) return false;
    std::error_code error;
    std::filesystem::remove_all(manifestPath.parent_path(), error);
    return !error;
}
