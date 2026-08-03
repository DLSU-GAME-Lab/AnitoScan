#include "editor/controller/PipelineController.h"

#include "editor/backend/BackendClient.h"

#include <type_traits>
#include <utility>
#include <variant>

namespace {
bool IsTerminalStatus(RunStatus status) {
    return status == RunStatus::Completed || status == RunStatus::Failed ||
        status == RunStatus::Cancelled;
}
}

PipelineController::PipelineController(BackendClient& backendClient)
    : backendClient_(backendClient) {}

const EditorState& PipelineController::GetState() const {
    return state_;
}

const RunState* PipelineController::GetSelectedRun() const {
    if (!state_.selectedRunId) {
        return nullptr;
    }

    return FindRun(*state_.selectedRunId);
}

RunId PipelineController::CreateRun(std::string name) {
    RunState run;
    run.id = "run-" + std::to_string(nextRunId_++);
    run.name = std::move(name);

    state_.runs.push_back(std::move(run));
    state_.selectedRunId = state_.runs.back().id;
    return state_.runs.back().id;
}

bool PipelineController::SelectRun(const RunId& runId) {
    if (FindRun(runId) == nullptr) {
        return false;
    }

    state_.selectedRunId = runId;
    return true;
}

void PipelineController::ClearSelection() {
    state_.selectedRunId.reset();
}

bool PipelineController::CompleteRun(const RunId& runId, std::filesystem::path outputModelPath) {
    RunState* run = FindRun(runId);
    if (run == nullptr ||
        (run->status != RunStatus::Running && run->status != RunStatus::Cancelling)) {
        return false;
    }

    run->status = RunStatus::Completed;
    run->phase = PipelinePhase::Export;
    run->outputModelPath = std::move(outputModelPath);
    run->selectionRequest.reset();
    run->errorMessage.reset();
    return true;
}

bool PipelineController::StartRun(const RunId& runId) {
    RunState* run = FindRun(runId);
    if (run == nullptr || run->status != RunStatus::Pending) {
        return false;
    }

    if (!state_.backendReady) {
        run->errorMessage = "Backend is not ready";
        return false;
    }

    for (const RunState& existingRun : state_.runs) {
        if (existingRun.status == RunStatus::Running ||
            existingRun.status == RunStatus::Cancelling) {
            run->errorMessage = "Another run is already active";
            return false;
        }
    }

    if (!backendClient_.StartRun(StartRunCommand{run->id, run->name})) {
        run->errorMessage = "Failed to send start command";
        return false;
    }

    run->errorMessage.reset();
    run->status = RunStatus::Running;
    return true;
}

bool PipelineController::CancelRun(const RunId& runId) {
    RunState* run = FindRun(runId);
    if (run == nullptr || run->status == RunStatus::Cancelling ||
        IsTerminalStatus(run->status)) {
        return false;
    }

    if (run->status == RunStatus::Pending) {
        run->status = RunStatus::Cancelled;
        run->selectionRequest.reset();
        run->errorMessage.reset();
        return true;
    }

    if (!backendClient_.CancelRun(CancelRunCommand{runId})) {
        run->errorMessage = "Failed to send cancel command";
        return false;
    }

    run->status = RunStatus::Cancelling;
    run->selectionRequest.reset();
    run->errorMessage.reset();
    return true;
}

bool PipelineController::SubmitSelection(const RunId& runId, std::optional<int> choice) {
    RunState* run = FindRun(runId);
    if (run == nullptr || run->status != RunStatus::Running || !run->selectionRequest) {
        return false;
    }

    if (!backendClient_.SubmitSelection(SubmitSelectionCommand{runId, choice})) {
        run->errorMessage = "Failed to send selection command";
        return false;
    }

    run->errorMessage.reset();
    run->selectionRequest.reset();
    return true;
}

void PipelineController::AddLog(std::string message) {
    state_.logs.push_back(std::move(message));
}

void PipelineController::HandleEvent(const BackendEvent& event) {
    std::visit([this](const auto& value) {
        using Event = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<Event, BackendReadyEvent>) {
            state_.backendReady = true;
            state_.logs.push_back("Backend ready");
        } else if constexpr (std::is_same_v<Event, LogEvent>) {
            state_.logs.push_back(value.text);
        } else {
            RunState* run = FindRun(value.runId);
            if (run == nullptr) {
                return;
            }

            if constexpr (std::is_same_v<Event, WorkspaceReadyEvent>) {
                if (!IsTerminalStatus(run->status)) {
                    run->workspacePath = value.workspacePath;
                }
            } else if constexpr (std::is_same_v<Event, ProgressEvent>) {
                if (run->status == RunStatus::Running) {
                    run->phase = value.phase;
                    run->progress = value.value;
                    run->progressLabel = value.label;
                }
            } else if constexpr (std::is_same_v<Event, SelectionRequiredEvent>) {
                if (run->status == RunStatus::Running) {
                    run->phase = PipelinePhase::Masking;
                    run->selectionRequest = SelectionRequest{
                        value.frame, value.previewPath, value.candidateCount
                    };
                }
            } else if constexpr (std::is_same_v<Event, RunCompletedEvent>) {
                CompleteRun(value.runId, value.outputModelPath);
            } else if constexpr (std::is_same_v<Event, RunFailedEvent>) {
                if (run->status == RunStatus::Running ||
                    run->status == RunStatus::Cancelling) {
                    run->status = RunStatus::Failed;
                    run->errorMessage = value.message;
                    run->selectionRequest.reset();
                }
            } else if constexpr (std::is_same_v<Event, RunCancelledEvent>) {
                if (run->status == RunStatus::Running ||
                    run->status == RunStatus::Cancelling) {
                    run->status = RunStatus::Cancelled;
                    run->selectionRequest.reset();
                    run->errorMessage.reset();
                }
            }
        }
    }, event);
}

RunState* PipelineController::FindRun(const RunId& runId) {
    for (RunState& run : state_.runs) {
        if (run.id == runId) {
            return &run;
        }
    }

    return nullptr;
}

const RunState* PipelineController::FindRun(const RunId& runId) const {
    for (const RunState& run : state_.runs) {
        if (run.id == runId) {
            return &run;
        }
    }

    return nullptr;
}
