#include "editor/protocol/BackendProtocol.h"

#include <nlohmann/json.hpp>

#include <utility>

namespace {

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

const char* PipelineModeText(PipelineMode mode) {
    return mode == PipelineMode::Pipe ? "pipe" : "disk";
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

std::optional<PipelinePhase> ParsePhase(int phase) {
    switch (phase) {
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
        return std::nullopt;
    }
}

} // namespace

std::string SerializeCommand(const StartRunCommand& command) {
    return nlohmann::json{
        {"action", "start_run"},
        {"run_id", command.runId},
        {"name", command.name},
        {"input", command.config.inputSource.string()},
        {"minimum_frames", command.config.minimumFrames},
        {"mode", PipelineModeText(command.config.mode)},
        {"capture_mode", CaptureModeText(command.config.captureMode)},
        {"quality", QualityText(command.config.quality)},
        {"force", command.config.force},
        {"iou_threshold", command.config.iouThreshold},
        {"drift_limit", command.config.driftLimit},
        {"yoloe_model_size", command.config.yoloModelSize},
    }.dump();
}

std::string SerializeCommand(const SubmitSelectionCommand& command) {
    nlohmann::json message = {{"action", "submit_selection"}, {"run_id", command.runId}};
    message["choice"] = command.choice ? nlohmann::json(*command.choice) : nlohmann::json(nullptr);
    return message.dump();
}

std::string SerializeCommand(const CancelRunCommand& command) {
    return nlohmann::json{{"action", "cancel_run"}, {"run_id", command.runId}}.dump();
}

std::string SerializeCommand(const AdvanceRunCommand& command) {
    return nlohmann::json{{"action", "continue_run"}, {"run_id", command.runId}}.dump();
}

std::optional<BackendEvent> ParseEvent(std::string_view message) {
    try {
        const nlohmann::json json = nlohmann::json::parse(message);
        if (!json.is_object() || !json.contains("type") || !json["type"].is_string()) {
            return std::nullopt;
        }

        const std::string type = json["type"].get<std::string>();
        if (type == "backend_ready") {
            return BackendReadyEvent{};
        }
        if (type == "log") {
            if (!json.contains("text") || !json["text"].is_string()) {
                return std::nullopt;
            }

            std::optional<RunId> runId;
            if (json.contains("run_id")) {
                if (!json["run_id"].is_string()) {
                    return std::nullopt;
                }
                runId = json["run_id"].get<RunId>();
            }
            return LogEvent{std::move(runId), json["text"].get<std::string>()};
        }

        if (!json.contains("run_id") || !json["run_id"].is_string()) {
            return std::nullopt;
        }
        const RunId runId = json["run_id"].get<RunId>();

        if (type == "workspace_ready") {
            if (!json.contains("workspace_path") || !json["workspace_path"].is_string()) {
                return std::nullopt;
            }
            return WorkspaceReadyEvent{runId, json["workspace_path"].get<std::string>()};
        }
        if (type == "progress") {
            if (!json.contains("phase") || !json["phase"].is_number_integer() ||
                !json.contains("value") || !json["value"].is_number() ||
                !json.contains("label") || !json["label"].is_string()) {
                return std::nullopt;
            }
            const auto phase = ParsePhase(json["phase"].get<int>());
            if (!phase) {
                return std::nullopt;
            }
            return ProgressEvent{runId, *phase, json["value"].get<float>(),
                                 json["label"].get<std::string>()};
        }
        if (type == "selection_required") {
            if (!json.contains("frame") || !json["frame"].is_string() ||
                !json.contains("preview_path") || !json["preview_path"].is_string() ||
                !json.contains("candidate_count") || !json["candidate_count"].is_number_integer()) {
                return std::nullopt;
            }
            return SelectionRequiredEvent{runId, json["frame"].get<std::string>(),
                                          json["preview_path"].get<std::string>(),
                                          json["candidate_count"].get<int>()};
        }
        if (type == "run_completed") {
            if (!json.contains("output_model_path") || !json["output_model_path"].is_string()) {
                return std::nullopt;
            }
            return RunCompletedEvent{runId, json["output_model_path"].get<std::string>()};
        }
        if (type == "run_failed") {
            if (!json.contains("message") || !json["message"].is_string()) {
                return std::nullopt;
            }
            return RunFailedEvent{runId, json["message"].get<std::string>()};
        }
        if (type == "run_cancelled") {
            return RunCancelledEvent{runId};
        }
        if (type == "phase_ready") {
            if (!json.contains("phase") || !json["phase"].is_number_integer()) {
                return std::nullopt;
            }
            const auto phase = ParsePhase(json["phase"].get<int>());
            if (!phase) {
                return std::nullopt;
            }
            return PhaseReadyEvent{runId, *phase};
        }
        return std::nullopt;
    } catch (...) {
        return std::nullopt;
    }
}
