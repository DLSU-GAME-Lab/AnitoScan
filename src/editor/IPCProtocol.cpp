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
		if (!j.is_object()) {
			return event;
		}

		std::string typeStr = j.value("type", "");

		if (typeStr == "backend_ready") {
			event.type = EventType::BACKEND_READY;
			event.backendReady.protocolVersion = j.value("protocol_version", 0);
		}
		else if (typeStr == "log") {
			event.type = EventType::LOG;
			event.log.text = j.value("text", "");
		}
		else if (typeStr == "workspace_ready") {
			event.type = EventType::WORKSPACE_READY;
			event.workspaceReady.runName = j.value("run_name", "");
			event.workspaceReady.workspace = j.value("workspace", "");
		}
		else if (typeStr == "phase_started") {
			event.type = EventType::PHASE_STARTED;
			event.phaseStarted.phase = IntToPhase(j.value("phase", 0));
			event.phaseStarted.label = j.value("label", "");
		}
		else if (typeStr == "progress") {
			event.type = EventType::PROGRESS;
			event.progress.phase = IntToPhase(j.value("phase", 0));
			event.progress.value = j.value("value", 0.0f);
			event.progress.overallValue = j.value("overall_value", 0.0f);
			event.progress.label = j.value("label", "");
		}
		else if (typeStr == "action_required") {
			event.type = EventType::ACTION_REQUIRED;
			event.actionRequired.requestId = j.value("request_id", "");
			event.actionRequired.action = j.value("action", "");
			event.actionRequired.phase = IntToPhase(j.value("phase", 0));
			event.actionRequired.frame = j.value("frame", "");
			event.actionRequired.preview = j.value("preview", "");
			event.actionRequired.count = j.value("count", 0);
		}
		else if (typeStr == "phase_completed") {
			event.type = EventType::PHASE_COMPLETED;
			event.phaseCompleted.phase = IntToPhase(j.value("phase", 0));
		}
		else if (typeStr == "done") {
			event.type = EventType::DONE;
			event.done.runName = j.value("run_name", "");
			event.done.workspace = j.value("workspace", "");
			event.done.output = j.value("output", "");
		}
		else if (typeStr == "cancelled") {
			event.type = EventType::CANCELLED;
			event.cancelled.runName = j.value("run_name", "");
		}
		else if (typeStr == "error") {
			event.type = EventType::ERROR;
			event.error.scope = j.value("scope", "command");
			event.error.code = j.value("code", "unknown");
			event.error.text = j.value("text", "");
			event.error.runName = j.value("run_name", "");
			if (j.contains("phase")) {
				event.error.phase = IntToPhase(j.at("phase").get<int>());
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
