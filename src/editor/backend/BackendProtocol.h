#pragma once

#include "editor/domain/PipelineTypes.h"

#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <variant>

struct StartRunCommand {
    RunId runId;
    std::string name;
};

struct SubmitSelectionCommand {
    RunId runId;
    std::optional<int> choice;
};

struct CancelRunCommand {
    RunId runId;
};



struct BackendReadyEvent {};

struct BackendDisconnectedEvent {
    std::string message;
};

struct LogEvent {
    std::optional<RunId> runId;
    std::string text;
};

struct WorkspaceReadyEvent {
    RunId runId;
    std::filesystem::path workspacePath;
};

struct ProgressEvent {
    RunId runId;
    PipelinePhase phase;
    float value;
    std::string label;
};

struct SelectionRequiredEvent {
    RunId runId;
    std::string frame;
    std::filesystem::path previewPath;
    int candidateCount;
};

struct RunCompletedEvent {
    RunId runId;
    std::filesystem::path outputModelPath;
};

struct RunFailedEvent {
    RunId runId;
    std::string message;
};

struct RunCancelledEvent {
    RunId runId;
};

using BackendEvent = std::variant<BackendReadyEvent, BackendDisconnectedEvent, LogEvent,
                                  WorkspaceReadyEvent, ProgressEvent, SelectionRequiredEvent,
                                  RunCompletedEvent, RunFailedEvent, RunCancelledEvent>;

std::string SerializeCommand(const StartRunCommand& command);
std::string SerializeCommand(const SubmitSelectionCommand& command);
std::string SerializeCommand(const CancelRunCommand& command);
std::optional<BackendEvent> ParseEvent(std::string_view message);
