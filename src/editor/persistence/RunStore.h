#pragma once

#include "editor/domain/RunState.h"

#include <filesystem>
#include <vector>

class RunStore {
public:
    explicit RunStore(std::filesystem::path runsDirectory);

    std::vector<RunState> LoadRuns() const;
    bool SaveRun(const RunState& run) const;

private:
    std::filesystem::path runsDirectory_;
};
