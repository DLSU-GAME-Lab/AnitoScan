#pragma once

#include "editor/domain/EditorState.h"

#include <cstdint>
#include <filesystem>
#include <string>

class PipelineController {
public:
    const EditorState& GetState() const;
    const RunState* GetSelectedRun() const;
    RunId CreateRun(std::string name);
    bool SelectRun(const RunId& runId);
    bool CompleteRun(const RunId& runId, std::filesystem::path outputModelPath);

private:
    RunState* FindRun(const RunId& runId);
    const RunState* FindRun(const RunId& runId) const;

    EditorState state_;
    std::uint64_t nextRunId_ = 1;
};
