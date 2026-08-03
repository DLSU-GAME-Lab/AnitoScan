#pragma once

#include "editor/domain/EditorState.h"

#include <cstdint>
#include <filesystem>
#include <string>

class PipelineController {
public:
    const EditorState& GetState() const;
    RunId CreateRun(std::string name);
    bool SelectRun(const RunId& runId);
    bool CompleteRun(const RunId& runId, std::filesystem::path outputModelPath);

private:
    RunState* FindRun(const RunId& runId);

    EditorState state_;
    std::uint64_t nextRunId_ = 1;
};
