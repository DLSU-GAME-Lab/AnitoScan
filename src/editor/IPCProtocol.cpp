#include "IPCProtocol.h"

namespace IPCProtocol {

Phase IntToPhase(int value) {
	if (value >= 0 && value <= 5) {
		return static_cast<Phase>(value);
	}
	return Phase::NONE;
}

std::string SerializeRunPipeline(
	const std::string& runName,
	const std::string& input,
	int minimumFrames,
	const std::string& quality) {
	nlohmann::json j;
	j["type"] = "run_pipeline";
	j["run_name"] = runName;
	j["input"] = input;
	j["minimum_frames"] = minimumFrames;
	j["quality"] = quality;
	return j.dump();
}

std::string SerializeSelection(const std::string& requestId, int choiceIndex) {
	nlohmann::json j;
	j["type"] = "selection";
	j["request_id"] = requestId;
	j["choice"] = choiceIndex;
	return j.dump();
}

std::string SerializeSelectionSkip(const std::string& requestId) {
	nlohmann::json j;
	j["type"] = "selection";
	j["request_id"] = requestId;
	j["choice"] = "skip";
	return j.dump();
}

std::string SerializeCancelPipeline(const std::string& runName) {
	nlohmann::json j;
	j["type"] = "cancel_pipeline";
	j["run_name"] = runName;
	return j.dump();
}

DecodedEvent DecodeEvent(const std::string& rawJsonLine) {
	DecodedEvent event;
	event.rawJson = rawJsonLine;

	try {
		auto j = nlohmann::json::parse(rawJsonLine);
		if (!j.is_object() || !j.contains("type") || !j["type"].is_string()) {
			return event;
		}

		std::string typeStr = j["type"].get<std::string>();

		if (typeStr == "backend_ready") {
			if (!j.contains("protocol_version") || !j["protocol_version"].is_number_integer()) {
				event.type = EventType::UNKNOWN;
				return event;
			}
			event.type = EventType::BACKEND_READY;
			event.backendReady.protocolVersion = j["protocol_version"].get<int>();
		}
		else if (typeStr == "log") {
			if (!j.contains("text") || !j["text"].is_string()) {
				event.type = EventType::UNKNOWN;
				return event;
			}
			event.type = EventType::LOG;
			event.log.text = j["text"].get<std::string>();
		}
		else if (typeStr == "workspace_ready") {
			if (!j.contains("run_name") || !j["run_name"].is_string() ||
			    !j.contains("workspace") || !j["workspace"].is_string()) {
				event.type = EventType::UNKNOWN;
				return event;
			}
			event.type = EventType::WORKSPACE_READY;
			event.workspaceReady.runName = j["run_name"].get<std::string>();
			event.workspaceReady.workspace = j["workspace"].get<std::string>();
		}
		else if (typeStr == "phase_started") {
			if (!j.contains("phase") || !j["phase"].is_number_integer()) {
				event.type = EventType::UNKNOWN;
				return event;
			}
			event.type = EventType::PHASE_STARTED;
			event.phaseStarted.phase = IntToPhase(j["phase"].get<int>());
			event.phaseStarted.label = j.value("label", "");
		}
		else if (typeStr == "progress") {
			if (!j.contains("phase") || !j["phase"].is_number_integer() ||
			    !j.contains("value") || !j["value"].is_number()) {
				event.type = EventType::UNKNOWN;
				return event;
			}
			event.type = EventType::PROGRESS;
			event.progress.phase = IntToPhase(j["phase"].get<int>());
			event.progress.value = j["value"].get<float>();
			event.progress.overallValue = j.value("overall_value", 0.0f);
			event.progress.label = j.value("label", "");
		}
		else if (typeStr == "action_required") {
			if (!j.contains("request_id") || !j["request_id"].is_string()) {
				event.type = EventType::UNKNOWN;
				return event;
			}
			event.type = EventType::ACTION_REQUIRED;
			event.actionRequired.requestId = j["request_id"].get<std::string>();
			event.actionRequired.action = j.value("action", "");
			event.actionRequired.phase = IntToPhase(j.value("phase", 0));
			event.actionRequired.frame = j.value("frame", "");
			event.actionRequired.preview = j.value("preview", "");
			event.actionRequired.count = j.value("count", 0);
		}
		else if (typeStr == "phase_completed") {
			if (!j.contains("phase") || !j["phase"].is_number_integer()) {
				event.type = EventType::UNKNOWN;
				return event;
			}
			event.type = EventType::PHASE_COMPLETED;
			event.phaseCompleted.phase = IntToPhase(j["phase"].get<int>());
		}
		else if (typeStr == "done") {
			if (!j.contains("run_name") || !j["run_name"].is_string()) {
				event.type = EventType::UNKNOWN;
				return event;
			}
			event.type = EventType::DONE;
			event.done.runName = j["run_name"].get<std::string>();
			event.done.workspace = j.value("workspace", "");
			event.done.output = j.value("output", "");
		}
		else if (typeStr == "cancelled") {
			if (!j.contains("run_name") || !j["run_name"].is_string()) {
				event.type = EventType::UNKNOWN;
				return event;
			}
			event.type = EventType::CANCELLED;
			event.cancelled.runName = j["run_name"].get<std::string>();
		}
		else if (typeStr == "error") {
			if (!j.contains("code") || !j["code"].is_string() ||
			    !j.contains("text") || !j["text"].is_string()) {
				event.type = EventType::UNKNOWN;
				return event;
			}
			event.type = EventType::ERROR;
			event.error.scope = j.value("scope", "command");
			event.error.code = j["code"].get<std::string>();
			event.error.text = j["text"].get<std::string>();
			event.error.runName = j.value("run_name", "");
			if (j.contains("phase") && j["phase"].is_number_integer()) {
				event.error.phase = IntToPhase(j["phase"].get<int>());
			}
			event.error.requestId = j.value("request_id", "");
		}
	}
	catch (const nlohmann::json::exception&) {
		event.type = EventType::UNKNOWN;
	}

	return event;
}

} // namespace IPCProtocol
