#pragma once

#include "editor/backend/BackendProtocol.h"
#include "editor/domain/EditorState.h"

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

class BackendClient;
class RunStore;

enum class CreateRunResult { Created, DuplicateName, InvalidName, StorageError };

class PipelineController {
public:
    PipelineController(BackendClient& backendClient, RunStore& runStore);

    const EditorState& GetState() const;
    const RunState* GetSelectedRun() const;
    CreateRunResult CreateRun(std::string name);
    void RestoreRuns(std::vector<RunState> runs);
    bool SelectRun(const RunId& runId);
    void ClearSelection();
    bool CompleteRun(const RunId& runId, std::filesystem::path outputModelPath);
    bool StartRun(const RunId& runId);
    bool CancelRun(const RunId& runId);
    bool SubmitSelection(const RunId& runId, std::optional<int> choice);
    void AddLog(std::string message);
    void HandleEvent(const BackendEvent& event);

private:
    RunState* FindRun(const RunId& runId);
    const RunState* FindRun(const RunId& runId) const;

    BackendClient& backendClient_;
    RunStore& runStore_;
    EditorState state_;
    std::uint64_t nextRunId_ = 1;
};
