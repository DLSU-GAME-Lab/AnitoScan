#include "editor/persistence/RunStore.h"

#include <algorithm>
#include <fstream>
#include <system_error>

#include <nlohmann/json.hpp>

namespace {

using Json = nlohmann::json;

int PhaseNumber(PipelinePhase phase) {
    switch (phase) {
    case PipelinePhase::Capture:
        return 1;
    case PipelinePhase::Masking:
        return 2;
    case PipelinePhase::Spatial:
        return 3;
    case PipelinePhase::Geometry:
        return 4;
    case PipelinePhase::Export:
        return 5;
    }
    return 0;
}

const char* CaptureModeText(CaptureMode mode) {
    switch (mode) {
    case CaptureMode::Auto:
        return "auto";
    case CaptureMode::Image:
        return "image";
    case CaptureMode::Video:
        return "video";
    }
    return "auto";
}

const char* QualityText(Quality quality) {
    switch (quality) {
    case Quality::Fast:
        return "fast";
    case Quality::Medium:
        return "medium";
    case Quality::Detailed:
        return "detailed";
    }
    return "fast";
}

const char* StatusText(RunStatus status) {
    switch (status) {
    case RunStatus::Pending:
        return "pending";
    case RunStatus::Running:
        return "running";
    case RunStatus::Cancelling:
        return "cancelling";
    case RunStatus::Completed:
        return "completed";
    case RunStatus::Failed:
        return "failed";
    case RunStatus::Cancelled:
        return "cancelled";
    }
    return "failed";
}

PipelinePhase ParsePhase(int phase) {
    switch (phase) {
    case 0:
    case 1:
        return PipelinePhase::Capture;
    case 2:
        return PipelinePhase::Masking;
    case 3:
        return PipelinePhase::Spatial;
    case 4:
        return PipelinePhase::Geometry;
    case 5:
        return PipelinePhase::Export;
    default:
        throw std::runtime_error("status.phase must be an integer from 0 through 5");
    }
}

std::optional<std::filesystem::path> FindOutputModel(const Json& paths) {
    std::error_code error;

    if (paths.contains("output_model")) {
        if (!paths["output_model"].is_string()) {
            throw std::runtime_error("paths.output_model must be a string");
        }

        std::filesystem::path model = paths["output_model"].get<std::string>();
        if (std::filesystem::is_regular_file(model, error) && !error) {
            return model;
        }
        return std::nullopt;
    }

    if (!paths.contains("export")) {
        return std::nullopt;
    }
    if (!paths["export"].is_string()) {
        throw std::runtime_error("paths.export must be a string");
    }

    const std::filesystem::path exportPath = paths["export"].get<std::string>();
    std::vector<std::filesystem::path> models;
    std::filesystem::recursive_directory_iterator iterator(
        exportPath,
        std::filesystem::directory_options::skip_permission_denied,
        error
    );
    const std::filesystem::recursive_directory_iterator end;
    while (!error && iterator != end) {
        const std::filesystem::directory_entry& entry = *iterator;
        std::error_code entryError;
        if (entry.is_regular_file(entryError) && !entryError && entry.path().extension() == ".obj") {
            models.push_back(entry.path());
        }
        iterator.increment(error);
    }

    if (models.empty()) {
        return std::nullopt;
    }
    std::sort(models.begin(), models.end());
    return models.front();
}

bool HasCompletedExport(const Json& status) {
    if (!status.contains("completed")) {
        return false;
    }
    if (!status["completed"].is_array()) {
        throw std::runtime_error("status.completed must be an array");
    }

    for (const Json& phase : status["completed"]) {
        if (!phase.is_string()) {
            throw std::runtime_error("status.completed entries must be strings");
        }
        if (phase.get<std::string>() == "export") {
            return true;
        }
    }
    return false;
}

RunState FailedRun(const std::filesystem::path& manifestPath, std::string message) {
    RunState run;
    run.id = manifestPath.parent_path().filename().string();
    run.name = run.id;
    run.status = RunStatus::Failed;
    run.workspacePath = manifestPath.parent_path();
    run.errorMessage = std::move(message);
    return run;
}

RunState ParseManifest(const std::filesystem::path& manifestPath) {
    std::ifstream input(manifestPath);
    if (!input) {
        throw std::runtime_error("Could not read manifest.json");
    }

    Json manifest;
    input >> manifest;
    if (!manifest.is_object()) {
        throw std::runtime_error("Manifest root must be an object");
    }

    const std::string fallbackId = manifestPath.parent_path().filename().string();
    const std::string id = manifest.value("run_id", fallbackId);
    const std::string name = manifest.value("run_name", id);
    if (id.empty()) {
        throw std::runtime_error("run_id must not be empty");
    }

    if (!manifest.contains("status") || !manifest["status"].is_object()) {
        throw std::runtime_error("status must be an object");
    }
    const Json& status = manifest["status"];
    if (!status.contains("phase") || !status["phase"].is_number_integer()) {
        throw std::runtime_error("status.phase must be an integer from 0 through 5");
    }
    const int phaseValue = status["phase"].get<int>();

    if (!manifest.contains("paths") || !manifest["paths"].is_object()) {
        throw std::runtime_error("paths must be an object");
    }
    const Json& paths = manifest["paths"];
    if (!paths.contains("run_root") || !paths["run_root"].is_string()) {
        throw std::runtime_error("paths.run_root must be a string");
    }

    RunState run;
    run.id = id;
    run.name = name;
    run.config.inputSource = manifest.value("input_source", "");
    run.config.mode = manifest.value("mode", "disk") == "pipe"
        ? PipelineMode::Pipe
        : PipelineMode::Disk;
    if (manifest.contains("settings") && manifest["settings"].is_object()) {
        const Json& settings = manifest["settings"];
        run.config.minimumFrames = settings.value("minimum_frames", 45);
        const std::string captureMode = settings.value("capture_mode", "auto");
        run.config.captureMode = captureMode == "image"
            ? CaptureMode::Image
            : captureMode == "video" ? CaptureMode::Video : CaptureMode::Auto;
        const std::string quality = settings.value("quality", "fast");
        run.config.quality = quality == "medium"
            ? Quality::Medium
            : quality == "detailed" ? Quality::Detailed : Quality::Fast;
        run.config.iouThreshold = settings.value("iou_threshold", 0.5f);
        run.config.driftLimit = settings.value("drift_limit", 200);
        run.config.yoloModelSize = settings.value("yoloe_model_size", "s");
        run.config.force = settings.value("force", false);
    }
    run.phase = ParsePhase(phaseValue);
    run.workspacePath = std::filesystem::path(paths["run_root"].get<std::string>());

    std::optional<std::string> state;
    if (status.contains("state")) {
        if (!status["state"].is_string()) {
            throw std::runtime_error("status.state must be a string");
        }
        state = status["state"].get<std::string>();
        if (*state != "completed" && *state != "failed" && *state != "cancelled" &&
            *state != "running" && *state != "cancelling" && *state != "pending") {
            throw std::runtime_error("status.state has an unsupported value");
        }
    }

    if (state == "pending") {
        run.status = RunStatus::Pending;
        return run;
    }
    if (state == "failed") {
        run.status = RunStatus::Failed;
        run.errorMessage = "Run previously failed";
        return run;
    }
    if (state == "cancelled") {
        run.status = RunStatus::Cancelled;
        return run;
    }

    if (state == "completed" || HasCompletedExport(status)) {
        run.outputModelPath = FindOutputModel(paths);
        if (run.outputModelPath) {
            run.status = RunStatus::Completed;
            run.phase = PipelinePhase::Export;
        } else {
            run.status = RunStatus::Failed;
            run.errorMessage = "Run completed, but no output .obj model exists";
        }
        return run;
    }

    run.status = RunStatus::Failed;
    run.errorMessage = "Run was interrupted";
    return run;
}

} // namespace

RunStore::RunStore(std::filesystem::path runsDirectory)
    : runsDirectory_(std::move(runsDirectory)) {}

std::vector<RunState> RunStore::LoadRuns() const {
    std::vector<std::filesystem::path> manifests;
    std::error_code error;
    std::filesystem::recursive_directory_iterator iterator(
        runsDirectory_,
        std::filesystem::directory_options::skip_permission_denied,
        error
    );
    const std::filesystem::recursive_directory_iterator end;
    while (!error && iterator != end) {
        const std::filesystem::directory_entry& entry = *iterator;
        std::error_code entryError;
        if (entry.is_regular_file(entryError) && !entryError && entry.path().filename() == "manifest.json") {
            manifests.push_back(entry.path());
        }
        iterator.increment(error);
    }
    std::sort(manifests.begin(), manifests.end());

    std::vector<RunState> runs;
    runs.reserve(manifests.size());
    for (const std::filesystem::path& manifestPath : manifests) {
        try {
            runs.push_back(ParseManifest(manifestPath));
        } catch (const std::exception& exception) {
            runs.push_back(FailedRun(manifestPath, std::string("Malformed manifest: ") + exception.what()));
        }
    }
    return runs;
}

bool RunStore::SaveRun(const RunState& run) const {
    const std::filesystem::path workspace = runsDirectory_ / run.name;
    const std::filesystem::path manifestPath = workspace / "manifest.json";
    const std::filesystem::path temporaryPath = workspace / "manifest.json.tmp";

    std::error_code error;
    std::filesystem::create_directories(workspace, error);
    if (error) {
        return false;
    }

    Json manifest = {
        {"run_id", run.id},
        {"run_name", run.name},
        {"input_source", run.config.inputSource.string()},
        {"mode", run.config.mode == PipelineMode::Pipe ? "pipe" : "disk"},
        {"settings", {
            {"minimum_frames", run.config.minimumFrames},
            {"capture_mode", CaptureModeText(run.config.captureMode)},
            {"quality", QualityText(run.config.quality)},
            {"force", run.config.force},
            {"iou_threshold", run.config.iouThreshold},
            {"drift_limit", run.config.driftLimit},
            {"yoloe_model_size", run.config.yoloModelSize},
        }},
        {"status", {
            {"state", StatusText(run.status)},
            {"phase", PhaseNumber(run.phase)},
            {"completed", Json::array()},
        }},
        {"paths", {
            {"run_root", workspace.string()},
        }},
    };
    if (run.outputModelPath) {
        manifest["paths"]["output_model"] = run.outputModelPath->string();
    }
    if (run.errorMessage) {
        manifest["error"] = *run.errorMessage;
    }

    std::ofstream output(temporaryPath);
    if (!output) {
        return false;
    }
    output << manifest.dump(4);
    output.close();
    if (!output) {
        return false;
    }

    std::filesystem::rename(temporaryPath, manifestPath, error);
    if (!error) {
        return true;
    }

    std::filesystem::remove(manifestPath, error);
    error.clear();
    std::filesystem::rename(temporaryPath, manifestPath, error);
    return !error;
}

bool RunStore::DeleteRun(const RunState& run) const {
    const std::filesystem::path name(run.name);
    if (run.name.empty() || name != name.filename() || run.name == "." || run.name == "..") {
        return false;
    }

    std::error_code error;
    std::filesystem::remove_all(runsDirectory_ / name, error);
    return !error;
}
