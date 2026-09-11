#include "editor/protocol/BackendProtocol.h"

#include <nlohmann/json.hpp>

#include <charconv>
#include <cmath>
#include <stdexcept>
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

// Internal selection payload: run ID, prompt ID, then index/-1 or bbox and four coordinates.
template<typename T>
T SelectionNumber(const std::string& text) {
    T result{};
    const auto parsed = std::from_chars(text.data(), text.data() + text.size(), result);
    if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size()) {
        throw std::invalid_argument("Invalid selection number");
    }
    return result;
}
}

std::string SerializeMessage(std::string_view type, std::string_view value) {
    const auto values = Split(value);
    nlohmann::json json;
    if (type == "start_run" && values.size() == 11) {
        json = {{"action", "start_run"}, {"run_id", values[0]}, {"name", values[1]}, {"input", values[2]}, {"minimum_frames", std::stoi(values[3])}, {"mode", values[4]}, {"capture_mode", values[5]}, {"quality", values[6]}, {"force", values[7] == "true"}, {"iou_threshold", std::stof(values[8])}, {"drift_limit", std::stoi(values[9])}, {"yoloe_model_size", values[10]}};
    } else if (type == "submit_selection") {
        if (values.size() < 3) return {};
        json = {{"action", "submit_selection"}, {"run_id", values[0]}};
        try {
            json["selection_id"] = SelectionNumber<int>(values[1]);
            if (values.size() == 3 && values[2] != "bbox") {
                json["choice"] = values[2] == "-1" ? nlohmann::json(nullptr) : nlohmann::json(SelectionNumber<int>(values[2]));
            } else if (values.size() == 7 && values[2] == "bbox") {
                auto box = nlohmann::json::array();
                for (std::size_t index = 3; index < 7; ++index) {
                    const double coordinate = SelectionNumber<double>(values[index]);
                    if (!std::isfinite(coordinate)) throw std::invalid_argument("Non-finite selection coordinate");
                    box.push_back(coordinate);
                }
                json["choice"] = {{"bbox", box}};
            } else {
                throw std::invalid_argument("Invalid selection payload");
            }
        } catch (const std::exception&) {
            // Let the backend reject this explicitly so the controller can restore the prompt.
            json["choice"] = {{"invalid", true}};
        }
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
        if (type == "selection_required") {
            const int width = json.at("image_width").get<int>();
            const int height = json.at("image_height").get<int>();
            const int selectionId = json.at("selection_id").get<int>();
            const int candidateCount = json.at("candidate_count").get<int>();
            if (width <= 0 || height <= 0 || selectionId <= 0 || candidateCount < 0) return std::nullopt;
            return ProtocolMessage{type, runId + "\n" + json.at("preview_path").get<std::string>() + "\n" + json.at("frame").get<std::string>() + "\n" + std::to_string(candidateCount) + "\n" + std::to_string(width) + "\n" + std::to_string(height) + "\n" + std::to_string(selectionId)};
        }
        if (type == "selection_accepted" || type == "selection_rejected") {
            std::string value = runId + "\n" + std::to_string(json.at("selection_id").get<int>());
            if (type == "selection_rejected") value += "\n" + json.at("message").get<std::string>();
            return ProtocolMessage{type, value};
        }
        if (type == "run_completed") return ProtocolMessage{type, runId + "\n" + json.at("output_model_path").get<std::string>()};
        if (type == "run_failed") return ProtocolMessage{type, runId + "\n" + json.at("message").get<std::string>()};
        if (type == "run_cancelled") return ProtocolMessage{type, runId};
    } catch (...) {
    }
    return std::nullopt;
}
