#include "editor/controller/PipelineController.h"


#include <algorithm>
#include <charconv>
#include <string_view>
#include <utility>

namespace {
std::vector<std::string> Split(std::string_view value) {
    std::vector<std::string> parts;
    std::size_t start = 0;
    while (start <= value.size()) {
        const std::size_t end = value.find('\n', start);
        parts.emplace_back(value.substr(start, end - start));
        if (end == std::string_view::npos) {
            break;
        }
        start = end + 1;
    }
    return parts;
}

bool IsCompleted(const RunSummary& summary) {
    return summary.status == "completed";
}
}


CreateRunResult PipelineController::CreateRun(std::string name, RunConfig config) {
    if (name.empty() || name == "." || name == "..") {
        return CreateRunResult::InvalidName;
    }
    if (config.inputSource.empty() || config.minimumFrames <= 0 || config.driftLimit < 0) {
        return CreateRunResult::InvalidConfig;
    }
    for (const RunSummary& summary : runSummaries_) {
        if (summary.name == name) {
            return CreateRunResult::DuplicateName;
        }
    }

    RunState run;
    run.id = "run-" + std::to_string(nextRunNumber_++);
    run.name = std::move(name);
    run.config = std::move(config);
    run.status = "pending";
    activeRun_ = std::move(run);
    currentPhaseData_.reset();
    phaseHistory_.clear();
    return CreateRunResult::Created;
}

void PipelineController::RestoreRuns(std::vector<RunSummary> summaries) {
    runSummaries_ = std::move(summaries);
    for (const RunSummary& summary : runSummaries_) {
        UpdateNextRunId(summary.id);
    }
}


void PipelineController::LoadRun(RunState run) {
    activeRun_ = std::move(run);
    currentPhaseData_.reset();
    phaseHistory_.clear();
}

void PipelineController::HandleBackendInput(const BackendInput& input) {
    if (input.type == "backend_disconnected") {
        backendAvailable_ = false;
        if (activeRun_ && (activeRun_->status == "running" || activeRun_->status == "cancelling")) {
            if (!currentPhaseData_) {
                currentPhaseData_ = PhaseData{};
            }
            currentPhaseData_->error = "Backend process disconnected";
            activeRun_->status = "failed";
            QueuePersistenceRequest("save", activeRun_->id);
            runSummaries_.push_back({activeRun_->id, activeRun_->name, activeRun_->status});
        }
        return;
    }

    if (input.type == "backend_ready") {
        backendAvailable_ = true;
        return;
    }
    if (!activeRun_) {
        return;
    }

    const std::vector<std::string> values = Split(input.value);
    if (input.type == "workspace_ready" && values.size() >= 2 && values[0] == activeRun_->id) {
        return;
    }
    if (input.type == "progress" && values.size() >= 4 && values[0] == activeRun_->id) {
        if (!currentPhaseData_) {
            currentPhaseData_ = PhaseData{};
        }
        currentPhaseData_->phaseName = values[1];
        currentPhaseData_->progress = std::stof(values[2]);
        currentPhaseData_->progressText = values[3];
        return;
    }
    if (input.type == "log" && values.size() >= 2) {
        if (!currentPhaseData_) {
            currentPhaseData_ = PhaseData{};
        }
        currentPhaseData_->logs.push_back(values.back());
        return;
    }
    if (input.type == "selection_required" && values.size() >= 4 && values[0] == activeRun_->id) {
        if (!currentPhaseData_) {
            currentPhaseData_ = PhaseData{};
        }
        currentPhaseData_->phaseName = "Masking";
        currentPhaseData_->previewPath = values[1];
        currentPhaseData_->candidateCount = std::stoi(values[3]);
        return;
    }
    if (input.type == "run_completed" && values.size() >= 2 && values[0] == activeRun_->id) {
        activeRun_->status = "completed";
        activeRun_->outputModelPath = values[1];
        QueuePersistenceRequest("save", activeRun_->id);
        runSummaries_.push_back({activeRun_->id, activeRun_->name, activeRun_->status});
        return;
    }
    if ((input.type == "run_failed" || input.type == "run_cancelled") &&
        !values.empty() && values[0] == activeRun_->id) {
        activeRun_->status = input.type == "run_failed" ? "failed" : "cancelled";
        if (input.type == "run_failed" && values.size() >= 2) {
            if (!currentPhaseData_) {
                currentPhaseData_ = PhaseData{};
            }
            currentPhaseData_->error = values[1];
        }
        QueuePersistenceRequest("save", activeRun_->id);
        runSummaries_.push_back({activeRun_->id, activeRun_->name, activeRun_->status});
    }
}

void PipelineController::StartRun(const std::string& runId) {
    if (!activeRun_ || activeRun_->id != runId || activeRun_->status != "pending") {
        return;
    }
    activeRun_->status = "running";
    QueuePersistenceRequest("save", activeRun_->id);
    QueueMessage("start_run", activeRun_->id + "\n" + activeRun_->name + "\n" +
        activeRun_->config.inputSource.string() + "\n" + std::to_string(activeRun_->config.minimumFrames) + "\n" +
        activeRun_->config.mode + "\n" + activeRun_->config.captureMode + "\n" +
        activeRun_->config.quality + "\n" + (activeRun_->config.force ? "true" : "false") + "\n" +
        std::to_string(activeRun_->config.iouThreshold) + "\n" + std::to_string(activeRun_->config.driftLimit) + "\n" +
        activeRun_->config.yoloModelSize);
}

void PipelineController::CancelRun(const std::string& runId) {
    if (!activeRun_ || activeRun_->id != runId) {
        return;
    }
    if (activeRun_->status == "pending") {
        activeRun_.reset();
        currentPhaseData_.reset();
        return;
    }
    if (activeRun_->status == "running") {
        activeRun_->status = "cancelling";
        QueueMessage("cancel_run", runId);
    }
}

void PipelineController::SubmitSelection(const std::string& runId, const std::string& selection) {
    if (activeRun_ && activeRun_->id == runId && activeRun_->status == "running") {
        if (currentPhaseData_) {
            currentPhaseData_->previewPath.clear();
            currentPhaseData_->candidateCount = 0;
        }
        QueueMessage("submit_selection", runId + "\n" + selection);
    }
}

void PipelineController::SelectRun(const std::string& runId) {
    const auto summary = std::find_if(runSummaries_.begin(), runSummaries_.end(), [&runId](const RunSummary& item) {
        return item.id == runId && IsCompleted(item);
    });
    if (summary == runSummaries_.end()) {
        return;
    }
    QueuePersistenceRequest("load", runId);
}

void PipelineController::DeleteRun(const std::string& runId) {
    QueuePersistenceRequest("delete", runId);
    std::erase_if(runSummaries_, [&runId](const RunSummary& item) { return item.id == runId; });
    if (activeRun_ && activeRun_->id == runId) {
        ClearActiveRun();
    }
}

void PipelineController::ClearActiveRun() {
    activeRun_.reset();
    currentPhaseData_.reset();
    phaseHistory_.clear();
}

void PipelineController::PrepareForShutdown() {
    if (!activeRun_) {
        return;
    }

    if (activeRun_->status == "pending") {
        ClearActiveRun();
        return;
    }

    if (activeRun_->status == "running" || activeRun_->status == "cancelling") {
        activeRun_->status = "cancelled";
        QueuePersistenceRequest("save", activeRun_->id);
    }
}

const std::vector<RunSummary>& PipelineController::GetRunSummaries() const { return runSummaries_; }
const RunState* PipelineController::GetActiveRun() const { return activeRun_ ? &*activeRun_ : nullptr; }
const PhaseData* PipelineController::GetCurrentPhaseData() const { return currentPhaseData_ ? &*currentPhaseData_ : nullptr; }
bool PipelineController::CanCreateRun() const { return backendAvailable_; }

std::vector<PipelineMessage> PipelineController::PollMessages() {
    std::vector<PipelineMessage> messages;
    messages.swap(outgoingMessages_);
    return messages;
}

std::vector<PersistenceRequest> PipelineController::PollPersistenceRequests() {
    std::vector<PersistenceRequest> requests;
    requests.swap(persistenceRequests_);
    return requests;
}

void PipelineController::QueueMessage(std::string type, std::string value) {
    outgoingMessages_.push_back({std::move(type), std::move(value)});
}

void PipelineController::QueuePersistenceRequest(std::string type, std::string runId) {
    persistenceRequests_.push_back({std::move(type), std::move(runId)});
}

void PipelineController::UpdateNextRunId(const std::string& runId) {
    constexpr std::string_view prefix = "run-";
    if (!runId.starts_with(prefix)) {
        return;
    }
    unsigned long long number = 0;
    const std::string_view suffix(runId.data() + prefix.size(), runId.size() - prefix.size());
    if (std::from_chars(suffix.data(), suffix.data() + suffix.size(), number).ec == std::errc{}) {
        nextRunNumber_ = std::max(nextRunNumber_, number + 1);
    }
}
