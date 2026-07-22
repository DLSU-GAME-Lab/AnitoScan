#pragma once

#include <string>
#include <nlohmann/json.hpp>
#include "Types.h"

namespace IPCProtocol {

constexpr int PROTOCOL_VERSION = 1;

enum class EventType {
	UNKNOWN,
	BACKEND_READY,
	LOG,
	WORKSPACE_READY,
	PHASE_STARTED,
	PROGRESS,
	ACTION_REQUIRED,
	PHASE_COMPLETED,
	DONE,
	CANCELLED,
	ERROR
};

// Command Serializers
std::string SerializeRunPipeline(
	const std::string& runName,
	const std::string& input,
	int minimumFrames,
	const std::string& quality);

std::string SerializeSelection(const std::string& requestId, int choiceIndex);
std::string SerializeSelectionSkip(const std::string& requestId);
std::string SerializeCancelPipeline(const std::string& runName);

// Event Structs
struct BackendReadyEvent {
	int protocolVersion = 0;
};

struct LogEvent {
	std::string text;
};

struct WorkspaceReadyEvent {
	std::string runName;
	std::string workspace;
};

struct PhaseStartedEvent {
	Phase phase = Phase::NONE;
	std::string label;
};

struct ProgressEvent {
	Phase phase = Phase::NONE;
	float value = 0.0f;
	float overallValue = 0.0f;
	std::string label;
};

struct ActionRequiredEvent {
	std::string requestId;
	std::string action;
	Phase phase = Phase::NONE;
	std::string frame;
	std::string preview;
	int count = 0;
};

struct PhaseCompletedEvent {
	Phase phase = Phase::NONE;
};

struct DoneEvent {
	std::string runName;
	std::string workspace;
	std::string output;
};

struct CancelledEvent {
	std::string runName;
};

struct ErrorEvent {
	std::string scope; // "command", "run", "backend"
	std::string code;
	std::string text;
	std::string runName;
	Phase phase = Phase::NONE;
	std::string requestId;
};

struct DecodedEvent {
	EventType type = EventType::UNKNOWN;
	std::string rawJson;

	BackendReadyEvent backendReady;
	LogEvent log;
	WorkspaceReadyEvent workspaceReady;
	PhaseStartedEvent phaseStarted;
	ProgressEvent progress;
	ActionRequiredEvent actionRequired;
	PhaseCompletedEvent phaseCompleted;
	DoneEvent done;
	CancelledEvent cancelled;
	ErrorEvent error;
};

DecodedEvent DecodeEvent(const std::string& rawJsonLine);
Phase IntToPhase(int value);

} // namespace IPCProtocol
