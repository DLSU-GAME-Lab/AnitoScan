#include "editor/persistence/RunStore.h"

#include <algorithm>
#include <cctype>
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

std::string ModelExtension(const std::filesystem::path& path) {
    std::string extension = path.extension().string();
    std::transform(extension.begin(), extension.end(), extension.begin(), [](unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    return extension;
}

void ReadRecordedOutputs(const Json& manifest, StoredRun& run) {
    const auto exports = manifest.find("exports");
    if (exports == manifest.end() || !exports->is_array()) return;

    // Export records are appended chronologically; restore the latest surviving output.
    for (auto it = exports->rbegin(); it != exports->rend(); ++it) {
        if (!it->is_object()) continue;
        const auto path = it->find("path");
        if (path == it->end() || !path->is_string()) continue;
        const std::filesystem::path outputPath = path->get<std::string>();
        const std::string extension = ModelExtension(outputPath);
        std::error_code error;
        if (!outputPath.is_absolute() || (extension != ".obj" && extension != ".glb") ||
            !std::filesystem::is_regular_file(outputPath, error)) continue;

        const std::string output = outputPath.string();
        if (std::find(run.outputModelPaths.begin(), run.outputModelPaths.end(), output) !=
            run.outputModelPaths.end()) continue;
        run.outputModelPaths.push_back(output);
        if (extension == ".obj") {
            run.outputPreviewPaths[output] = output;
            continue;
        }

        const auto preview = it->find("preview_path");
        if (preview == it->end() || !preview->is_string()) continue;
        const std::filesystem::path previewPath = preview->get<std::string>();
        if (previewPath.is_absolute() && ModelExtension(previewPath) == ".obj" &&
            std::filesystem::is_regular_file(previewPath, error)) {
            run.outputPreviewPaths[output] = previewPath.string();
        }
    }
}

void AddOutputModels(
    std::vector<std::string>& outputModels,
    const std::filesystem::path& outputDirectory
) {
    std::error_code error;
    if (!std::filesystem::is_directory(outputDirectory, error)) return;

    for (std::filesystem::directory_iterator it(outputDirectory, error), end; !error && it != end; it.increment(error)) {
        const std::string extension = ModelExtension(it->path());
        if (it->is_regular_file(error) && (extension == ".obj" || extension == ".glb")) {
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

    if (manifest.contains("exports") || manifest.contains("export_pending")) {
        // Prepared meshes are not final exports, even when export is still pending.
        ReadRecordedOutputs(manifest, run);
    } else {
        run.outputModelPaths = FindOutputModels(manifest, run.name, localOutputDirectory);
        for (const std::string& output : run.outputModelPaths) {
            if (ModelExtension(output) == ".obj") {
                run.outputPreviewPaths[output] = output;
            }
        }
    }
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

    const std::filesystem::path workspacePath = manifestPath.parent_path();
    std::string runName = workspacePath.filename().string();
    try {
        std::ifstream input(manifestPath);
        Json manifest;
        if (input >> manifest) {
            const auto manifestRunName = manifest.find("run_name");
            if (manifestRunName != manifest.end() && manifestRunName->is_string() &&
                !manifestRunName->get_ref<const std::string&>().empty()) {
                runName = manifestRunName->get<std::string>();
            }
        }
    } catch (...) {}

    const std::filesystem::path outputRoot =
        (runsDirectory_.parent_path() / "output").lexically_normal();
    const std::filesystem::path outputPath = (outputRoot / runName).lexically_normal();
    const bool outputPathIsDirectChild =
        outputPath != outputRoot && outputPath.parent_path() == outputRoot;

    std::error_code workspaceError;
    std::filesystem::remove_all(workspacePath, workspaceError);

    std::error_code outputError;
    if (outputPathIsDirectChild) {
        std::filesystem::remove_all(outputPath, outputError);
    }

    return !workspaceError && outputPathIsDirectChild && !outputError;
}
