#include "editor/controller/PipelineController.h"

#include "editor/backend/BackendClient.h"
#include "editor/persistence/RunStore.h"

#include <algorithm>
#include <string_view>
#include <type_traits>
#include <utility>
#include <variant>

namespace {
bool IsTerminalStatus(RunStatus status) {
    return status == RunStatus::Completed || status == RunStatus::Failed ||
        status == RunStatus::Cancelled;
}

bool IsValidRunConfig(const RunConfig& config) {
    const bool validModelSize = config.yoloModelSize == "n" || config.yoloModelSize == "s" ||
        config.yoloModelSize == "m" || config.yoloModelSize == "l" || config.yoloModelSize == "x";
    return !config.inputSource.empty() && config.minimumFrames > 0 &&
        config.iouThreshold >= 0.0f && config.iouThreshold <= 1.0f &&
        config.driftLimit >= 0 && validModelSize;
}

bool IsValidRunName(std::string_view name) {
    if (name.empty() || name == "." || name == ".." || name.back() == ' ' || name.back() == '.') {
        return false;
    }

    constexpr std::string_view forbidden = "<>:\"/\\|?*";
    for (const unsigned char character : name) {
        if (character < 32 || forbidden.find(character) != std::string_view::npos) {
            return false;
        }
    }
    return true;
}
} 

PipelineController::PipelineController(BackendClient& backendClient, RunStore& runStore)
    : backendClient_(backendClient), runStore_(runStore) {}

const EditorState& PipelineController::GetState() const {
    return state_;
}

const RunState* PipelineController::GetSelectedRun() const {
    if (!state_.selectedRunId) {
        return nullptr;
    }

    return FindRun(*state_.selectedRunId);
}

CreateRunResult PipelineController::CreateRun(std::string name, RunConfig config) {
    if (!IsValidRunName(name)) {
        return CreateRunResult::InvalidName;
    }
    if (!IsValidRunConfig(config)) {
        return CreateRunResult::InvalidConfig;
    }

    for (const RunState& existingRun : state_.runs) {
        if (existingRun.name == name) {
            return CreateRunResult::DuplicateName;
        }
    }

    RunState run;
    do {
        run.id = "run-" + std::to_string(nextRunId_++);
    } while (FindRun(run.id) != nullptr);
    run.name = std::move(name);
    run.config = std::move(config);
    if (!runStore_.SaveRun(run)) {
        return CreateRunResult::StorageError;
    }

    state_.runs.push_back(std::move(run));
    state_.selectedRunId = state_.runs.back().id;
    return CreateRunResult::Created;
}

void PipelineController::RestoreRuns(std::vector<RunState> runs) {
    for (RunState& run : runs) {
        bool duplicate = false;
        for (const RunState& existingRun : state_.runs) {
            if (existingRun.id == run.id || existingRun.name == run.name) {
                duplicate = true;
                break;
            }
        }
        if (!duplicate) {
            state_.runs.push_back(std::move(run));
        }
    }
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
    run->awaitingAdvance = false;
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

    if (!backendClient_.StartRun(StartRunCommand{run->id, run->name, run->config})) {
        run->errorMessage = "Failed to send start command";
        return false;
    }

    run->errorMessage.reset();
    run->status = RunStatus::Running;
    return true;
}

bool PipelineController::AdvanceRun(const RunId& runId) {
    RunState* run = FindRun(runId);
    if (run == nullptr || run->status != RunStatus::Running || !run->awaitingAdvance) {
        return false;
    }

    if (!backendClient_.AdvanceRun(AdvanceRunCommand{runId})) {
        run->errorMessage = "Failed to send continue command";
        return false;
    }

    run->awaitingAdvance = false;
    run->errorMessage.reset();
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
        if (!runStore_.SaveRun(*run)) {
            run->status = RunStatus::Pending;
            run->errorMessage = "Failed to save cancelled run";
            return false;
        }
        return true;
    }

    if (!backendClient_.CancelRun(CancelRunCommand{runId})) {
        run->errorMessage = "Failed to send cancel command";
        return false;
    }

    run->status = RunStatus::Cancelling;
    run->awaitingAdvance = false;
    run->selectionRequest.reset();
    run->errorMessage.reset();
    return true;
}

bool PipelineController::RetryRun(const RunId& runId) {
    RunState* run = FindRun(runId);
    if (run == nullptr || (run->status != RunStatus::Failed && run->status != RunStatus::Cancelled)) {
        return false;
    }

    const RunStatus previousStatus = run->status;
    run->status = RunStatus::Pending;
    run->phase = PipelinePhase::Capture;
    run->progress = 0.0f;
    run->progressLabel.clear();
    run->awaitingAdvance = false;
    run->selectionRequest.reset();
    run->errorMessage.reset();
    run->outputModelPath.reset();
    if (!runStore_.SaveRun(*run)) {
        run->status = previousStatus;
        run->errorMessage = "Failed to save retried run";
        return false;
    }
    return true;
}

bool PipelineController::DeleteRun(const RunId& runId) {
    RunState* run = FindRun(runId);
    if (run == nullptr || run->status == RunStatus::Running || run->status == RunStatus::Cancelling) {
        return false;
    }
    if (!runStore_.DeleteRun(*run)) {
        run->errorMessage = "Failed to delete run";
        return false;
    }

    if (state_.selectedRunId == runId) {
        state_.selectedRunId.reset();
    }
    std::erase_if(state_.runs, [&runId](const RunState& existingRun) {
        return existingRun.id == runId;
    });
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
        } else if constexpr (std::is_same_v<Event, BackendDisconnectedEvent>) {
            state_.backendReady = false;
            state_.logs.push_back(value.message);
            for (RunState& run : state_.runs) {
                if (run.status == RunStatus::Running || run.status == RunStatus::Cancelling) {
                    run.status = RunStatus::Failed;
                    run.awaitingAdvance = false;
                    run.errorMessage = value.message;
                    run.selectionRequest.reset();
                }
            }
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
                    run->awaitingAdvance = false;
                    run->errorMessage = value.message;
                    run->selectionRequest.reset();
                }
            } else if constexpr (std::is_same_v<Event, RunCancelledEvent>) {
                if (run->status == RunStatus::Running ||
                    run->status == RunStatus::Cancelling) {
                    run->status = RunStatus::Cancelled;
                    run->awaitingAdvance = false;
                    run->selectionRequest.reset();
                    run->errorMessage.reset();
                }
            } else if constexpr (std::is_same_v<Event, PhaseReadyEvent>) {
                if (run->status == RunStatus::Running) {
                    run->phase = value.phase;
                    run->progress = 0.0f;
                    run->progressLabel = "Ready to continue";
                    run->awaitingAdvance = true;
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
