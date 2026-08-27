#include "editor/protocol/BackendProtocol.h"

#include <nlohmann/json.hpp>

#include <vector>

namespace {
std::vector<std::string> Split(std::string_view value) {
    std::vector<std::string> parts;
    std::size_t start = 0;
    while (start <= value.size()) {
        const std::size_t end = value.find('\n', start);
        parts.emplace_back(value.substr(start, end - start));
        if (end == std::string_view::npos) break;
        start = end + 1;
    }
    return parts;
}
}

std::string SerializeMessage(std::string_view type, std::string_view value) {
    const auto values = Split(value);
    nlohmann::json json;
    if (type == "start_run" && values.size() == 11) {
        json = {{"action", "start_run"}, {"run_id", values[0]}, {"name", values[1]}, {"input", values[2]}, {"minimum_frames", std::stoi(values[3])}, {"mode", values[4]}, {"capture_mode", values[5]}, {"quality", values[6]}, {"force", values[7] == "true"}, {"iou_threshold", std::stof(values[8])}, {"drift_limit", std::stoi(values[9])}, {"yoloe_model_size", values[10]}};
    } else if (type == "submit_selection" && values.size() == 2) {
        json = {{"action", "submit_selection"}, {"run_id", values[0]}};
        json["choice"] = values[1] == "-1" ? nlohmann::json(nullptr) : nlohmann::json(std::stoi(values[1]));
    } else if (type == "cancel_run") {
        json = {{"action", "cancel_run"}, {"run_id", value}};
    } else {
        return {};
    }
    return json.dump();
}

std::optional<ProtocolMessage> ParseMessage(std::string_view message) {
    try {
        const auto json = nlohmann::json::parse(message);
        const std::string type = json.at("type").get<std::string>();
        if (type == "backend_ready") return ProtocolMessage{type, ""};
        const std::string runId = json.value("run_id", "");
        if (type == "log") return ProtocolMessage{type, runId + "\n" + json.at("text").get<std::string>()};
        if (type == "workspace_ready") return ProtocolMessage{type, runId + "\n" + json.at("workspace_path").get<std::string>()};
        if (type == "phase_started") return ProtocolMessage{type, runId + "\n" + std::to_string(json.at("phase").get<int>())};
        if (type == "progress") return ProtocolMessage{type, runId + "\n" + std::to_string(json.at("phase").get<int>()) + "\n" + std::to_string(json.at("value").get<float>()) + "\n" + json.at("label").get<std::string>()};
        if (type == "selection_required") return ProtocolMessage{type, runId + "\n" + json.at("preview_path").get<std::string>() + "\n" + json.at("frame").get<std::string>() + "\n" + std::to_string(json.at("candidate_count").get<int>())};
        if (type == "run_completed") return ProtocolMessage{type, runId + "\n" + json.at("output_model_path").get<std::string>()};
        if (type == "run_failed") return ProtocolMessage{type, runId + "\n" + json.at("message").get<std::string>()};
        if (type == "run_cancelled") return ProtocolMessage{type, runId};
    } catch (...) {
    }
    return std::nullopt;
}
