#include "editor/controller/PipelineController.h"

#include <utility>

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

bool PipelineController::CompleteRun(const RunId& runId, std::filesystem::path outputModelPath) {
    RunState* run = FindRun(runId);
    if (run == nullptr || run->status == RunStatus::Completed ||
        run->status == RunStatus::Failed || run->status == RunStatus::Cancelled) {
        return false;
    }

    run->status = RunStatus::Completed;
    run->phase = PipelinePhase::Export;
    run->outputModelPath = std::move(outputModelPath);
    return true;
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
