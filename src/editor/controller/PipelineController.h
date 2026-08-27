#pragma once

#include "editor/controller/ControllerTypes.h"

#include <cstddef>
#include <optional>
#include <string>
#include <vector>


enum class CreateRunResult {
    Created,
    DuplicateName,
    InvalidName,
    InvalidConfig,
    StorageError
};

class PipelineController {
public:
    PipelineController() = default;

    CreateRunResult CreateRun(std::string name, RunConfig config);

    void RestoreRuns(std::vector<RunSummary> summaries);
    void LoadRun(RunState run);

    void HandleBackendInput(const BackendInput& input);

    void StartRun(const std::string& runId);
    void CancelRun(const std::string& runId);
    void SubmitSelection(const std::string& runId, const std::string& selection);
    void SelectRun(const std::string& runId);
    void DeleteRun(const std::string& runId);
    void ClearActiveRun();
    void ViewPreviousPhase();
    void ViewNextPhase();
    void FollowLivePhase();
    void StopFollowingLivePhase();
    void PrepareForShutdown();

    const std::vector<RunSummary>& GetRunSummaries() const;
    const RunState* GetActiveRun() const;
    PhaseDisplayData GetPhaseDisplayData() const;
    PhaseNavigationData GetPhaseNavigationData() const;
    bool CanCreateRun() const;

    std::vector<PipelineMessage> PollMessages();
    std::vector<PersistenceRequest> PollPersistenceRequests();

private:
    void BeginPhaseIfNeeded(const std::string& phaseName);
    void CommitLivePhase();
    void ResetPhaseView();
    const PhaseData* GetViewedPhase() const;
    bool CanViewPreviousPhase() const;
    bool CanViewNextPhase() const;
    void QueueMessage(std::string type, std::string value);
    void QueuePersistenceRequest(std::string type, std::string runId);
    void UpdateNextRunId(const std::string& runId);


    std::optional<RunState> activeRun_;
    std::vector<RunSummary> runSummaries_;
    std::vector<PhaseData> phaseHistory_;
    std::optional<PhaseData> currentPhaseData_;
    std::size_t viewedPhaseIndex_ = 0;
    bool viewingLatest_ = true;
    std::vector<PipelineMessage> outgoingMessages_;
    std::vector<PersistenceRequest> persistenceRequests_;
    unsigned long long nextRunNumber_ = 1;
    bool backendAvailable_ = false;
};
