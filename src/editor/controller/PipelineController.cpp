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

std::string PhaseTitle(const std::string& phaseName) {
    if (phaseName == "1") return "Capture";
    if (phaseName == "2") return "Masking";
    if (phaseName == "3") return "Spatial";
    if (phaseName == "4") return "Geometry";
    if (phaseName == "5") return "Export";
    return phaseName;
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
    ResetPhaseView();
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
    ResetPhaseView();
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
        BeginPhaseIfNeeded(values[1]);
        currentPhaseData_->progress = std::stof(values[2]);
        currentPhaseData_->progressText = values[3];
        return;
    }
    if (input.type == "log" && values.size() >= 2 && values[0] == activeRun_->id) {
        if (!currentPhaseData_) {
            currentPhaseData_ = PhaseData{};
        }
        currentPhaseData_->logs.push_back(values.back());
        return;
    }
    if (input.type == "selection_required" && values.size() >= 4 && values[0] == activeRun_->id) {
        BeginPhaseIfNeeded("2");
        currentPhaseData_->previewPath = values[1];
        currentPhaseData_->candidateCount = std::stoi(values[3]);
        return;
    }
    if (input.type == "run_completed" && values.size() >= 2 && values[0] == activeRun_->id) {
        CommitLivePhase();
        currentPhaseData_.reset();
        activeRun_->status = "completed";
        activeRun_->outputModelPaths = {values[1]};
        activeRun_->outputModelPath = values[1];
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
        runSummaries_.push_back({activeRun_->id, activeRun_->name, activeRun_->status});
    }
}

void PipelineController::StartRun(const std::string& runId) {
    if (!activeRun_ || activeRun_->id != runId || activeRun_->status != "pending") {
        return;
    }
    activeRun_->status = "running";
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
        ResetPhaseView();
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

void PipelineController::SelectOutputModel(const std::string& runId, const std::string& path) {
    if (!activeRun_ || activeRun_->id != runId ||
        std::find(activeRun_->outputModelPaths.begin(), activeRun_->outputModelPaths.end(), path) ==
            activeRun_->outputModelPaths.end()) {
        return;
    }
    activeRun_->outputModelPath = path;
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
    ResetPhaseView();
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
    }
}

void PipelineController::ViewPreviousPhase() {
    if (!CanViewPreviousPhase()) {
        return;
    }
    if (viewingLatest_) {
        viewingLatest_ = false;
        viewedPhaseIndex_ = phaseHistory_.size() - 1;
    } else {
        --viewedPhaseIndex_;
    }
}

void PipelineController::ViewNextPhase() {
    if (!CanViewNextPhase()) {
        return;
    }
    const bool opensPostExport = activeRun_ && activeRun_->status == "completed" &&
        viewedPhaseIndex_ + 1 == phaseHistory_.size();
    if (opensPostExport) {
        viewingLatest_ = true;
        return;
    }
    ++viewedPhaseIndex_;
}

void PipelineController::FollowLivePhase() {
    viewingLatest_ = true;
}

void PipelineController::StopFollowingLivePhase() {
    if (!viewingLatest_ || !currentPhaseData_) {
        return;
    }
    viewingLatest_ = false;
    viewedPhaseIndex_ = phaseHistory_.size();
}

const std::vector<RunSummary>& PipelineController::GetRunSummaries() const { return runSummaries_; }
const RunState* PipelineController::GetActiveRun() const { return activeRun_ ? &*activeRun_ : nullptr; }

PhaseDisplayData PipelineController::GetPhaseDisplayData() const {
    PhaseDisplayData display;
    if (!activeRun_) {
        return display;
    }

    display.runId = activeRun_->id;
    display.runName = activeRun_->name;
    display.statusText = activeRun_->status;
    display.navigation = GetPhaseNavigationData();

    const PhaseData* phase = GetViewedPhase();
    if (!phase) {
        return display;
    }

    display.phaseText = PhaseTitle(phase->phaseName);
    display.progressText = phase->progressText;
    display.progress = phase->progress;
    display.previewPath = phase->previewPath;
    display.candidateCount = phase->candidateCount;
    display.logs = phase->logs;
    display.errorText = phase->error;

    if (!phase->error.empty()) {
        display.kind = PhaseDisplayKind::Error;
    } else if (!phase->previewPath.empty() || phase->candidateCount > 0) {
        display.kind = PhaseDisplayKind::MaskSelection;
    } else if (!phase->progressText.empty() || phase->progress > 0.0f) {
        display.kind = PhaseDisplayKind::Progress;
    } else {
        display.kind = PhaseDisplayKind::Processing;
    }
    const bool viewingLivePhase = currentPhaseData_ && phase == &*currentPhaseData_;
    display.maskSelectionEnabled = viewingLivePhase && activeRun_->status == "running" &&
        display.kind == PhaseDisplayKind::MaskSelection;
    return display;
}

PhaseNavigationData PipelineController::GetPhaseNavigationData() const {
    PhaseNavigationData navigation;
    navigation.viewingLatest = viewingLatest_;
    navigation.canGoBack = CanViewPreviousPhase();
    navigation.canGoNext = CanViewNextPhase();
    const bool completed = activeRun_ && activeRun_->status == "completed";
    navigation.canFollowLive = !viewingLatest_ && !completed;
    navigation.canStopFollowingLive = viewingLatest_ && currentPhaseData_.has_value();
    return navigation;
}

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

void PipelineController::BeginPhaseIfNeeded(const std::string& phaseName) {
    if (!currentPhaseData_) {
        currentPhaseData_ = PhaseData{};
    }
    if (currentPhaseData_->phaseName.empty()) {
        currentPhaseData_->phaseName = phaseName;
        return;
    }
    if (currentPhaseData_->phaseName != phaseName) {
        CommitLivePhase();
        currentPhaseData_ = PhaseData{};
        currentPhaseData_->phaseName = phaseName;
    }
}

void PipelineController::CommitLivePhase() {
    if (currentPhaseData_ && !currentPhaseData_->phaseName.empty()) {
        phaseHistory_.push_back(*currentPhaseData_);
    }
}

void PipelineController::ResetPhaseView() {
    phaseHistory_.clear();
    currentPhaseData_.reset();
    viewedPhaseIndex_ = 0;
    viewingLatest_ = true;
}

const PhaseData* PipelineController::GetViewedPhase() const {
    if (viewingLatest_) {
        return currentPhaseData_ ? &*currentPhaseData_ : nullptr;
    }
    if (viewedPhaseIndex_ < phaseHistory_.size()) {
        return &phaseHistory_[viewedPhaseIndex_];
    }
    if (viewedPhaseIndex_ == phaseHistory_.size() && currentPhaseData_) {
        return &*currentPhaseData_;
    }
    return nullptr;
}

bool PipelineController::CanViewPreviousPhase() const {
    return viewingLatest_ ? !phaseHistory_.empty() : viewedPhaseIndex_ > 0;
}

bool PipelineController::CanViewNextPhase() const {
    if (viewingLatest_) {
        return false;
    }
    if (viewedPhaseIndex_ + 1 < phaseHistory_.size()) {
        return true;
    }
    const bool completed = activeRun_ && activeRun_->status == "completed";
    if (completed && viewedPhaseIndex_ + 1 == phaseHistory_.size()) {
        return true;
    }
    return currentPhaseData_ && viewedPhaseIndex_ + 1 == phaseHistory_.size();
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
