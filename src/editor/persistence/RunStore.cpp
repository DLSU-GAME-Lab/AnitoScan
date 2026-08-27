#include "editor/persistence/RunStore.h"

#include <algorithm>
#include <fstream>
#include <nlohmann/json.hpp>
#include <vector>

namespace {
using Json = nlohmann::json;

std::filesystem::path FindManifest(const std::filesystem::path& root, const std::string& runId) {
    std::error_code error;
    for (std::filesystem::recursive_directory_iterator it(root, error), end; !error && it != end; it.increment(error)) {
        if (it->path().filename() != "manifest.json") continue;
        std::ifstream input(it->path());
        Json manifest;
        if (input >> manifest &&
            manifest.value("run_id", it->path().parent_path().filename().string()) == runId) {
            return it->path();
        }
    }
    return {};
}

int ModelQualityRank(const std::string& path) {
    const std::string filename = std::filesystem::path(path).stem().string();
    if (filename.ends_with("_fast")) return 0;
    if (filename.ends_with("_medium")) return 1;
    if (filename.ends_with("_detailed")) return 2;
    return 3;
}

void AddOutputModels(
    std::vector<std::string>& outputModels,
    const std::filesystem::path& outputDirectory
) {
    std::error_code error;
    if (!std::filesystem::is_directory(outputDirectory, error)) return;

    for (std::filesystem::directory_iterator it(outputDirectory, error), end; !error && it != end; it.increment(error)) {
        if (it->is_regular_file(error) && it->path().extension() == ".obj") {
            std::error_code canonicalError;
            const std::filesystem::path canonicalPath = std::filesystem::weakly_canonical(it->path(), canonicalError);
            outputModels.push_back((canonicalError ? it->path().lexically_normal() : canonicalPath).string());
        }
        error.clear();
    }
}

std::vector<std::string> FindOutputModels(
    const Json& manifest,
    const std::string& runName,
    const std::filesystem::path& localOutputDirectory
) {
    std::vector<std::string> outputModels;
    const auto paths = manifest.find("paths");
    if (paths != manifest.end() && paths->is_object()) {
        const auto exportPath = paths->find("export");
        if (exportPath != paths->end() && exportPath->is_string() &&
            !exportPath->get_ref<const std::string&>().empty()) {
            AddOutputModels(outputModels, exportPath->get<std::string>());
        }
    }

    AddOutputModels(outputModels, localOutputDirectory / runName);

    std::sort(outputModels.begin(), outputModels.end());
    outputModels.erase(std::unique(outputModels.begin(), outputModels.end()), outputModels.end());
    std::stable_sort(outputModels.begin(), outputModels.end(), [](const std::string& left, const std::string& right) {
        return ModelQualityRank(left) < ModelQualityRank(right);
    });
    return outputModels;
}

StoredRun ReadRun(
    const std::filesystem::path& manifestPath,
    const std::filesystem::path& localOutputDirectory
) {
    std::ifstream input(manifestPath);
    Json manifest;
    input >> manifest;
    StoredRun run;
    run.id = manifest.value("run_id", manifestPath.parent_path().filename().string());
    run.name = manifest.value("run_name", run.id);
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

    run.outputModelPaths = FindOutputModels(manifest, run.name, localOutputDirectory);
    run.status = run.outputModelPaths.empty() ? "failed" : "completed";
    if (!run.outputModelPaths.empty()) {
        run.outputModelPath = run.outputModelPaths.front();
    }
    return run;
}
}

RunStore::RunStore(std::filesystem::path runsDirectory) : runsDirectory_(std::move(runsDirectory)) {}

std::vector<StoredRun> RunStore::LoadRuns() const {
    std::vector<StoredRun> runs;
    std::error_code error;
    for (std::filesystem::recursive_directory_iterator it(runsDirectory_, error), end; !error && it != end; it.increment(error)) {
        if (it->path().filename() != "manifest.json") continue;
        try { runs.push_back(ReadRun(it->path(), runsDirectory_.parent_path() / "output")); } catch (...) {}
    }
    std::sort(runs.begin(), runs.end(), [](const StoredRun& left, const StoredRun& right) { return left.name < right.name; });
    return runs;
}

bool RunStore::LoadRun(const std::string& runId, StoredRun& run) const {
    const std::filesystem::path manifestPath = FindManifest(runsDirectory_, runId);
    if (manifestPath.empty()) return false;
    try { run = ReadRun(manifestPath, runsDirectory_.parent_path() / "output"); return true; } catch (...) { return false; }
}


bool RunStore::DeleteRun(const std::string& runId) const {
    const std::filesystem::path manifestPath = FindManifest(runsDirectory_, runId);
    if (manifestPath.empty()) return false;
    std::error_code error;
    std::filesystem::remove_all(manifestPath.parent_path(), error);
    return !error;
}
