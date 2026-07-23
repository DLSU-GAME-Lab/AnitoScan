#pragma once

#include <filesystem>

#include "Phase.h"

inline std::filesystem::path WorkspacePathForPhase(
	const std::filesystem::path& workspace,
	Phase phase) {
	std::filesystem::path phaseDirectory;
	switch (phase) {
		case Phase::CAPTURE: phaseDirectory = "01_capture"; break;
		case Phase::MASKING: phaseDirectory = "02_masking"; break;
		case Phase::SPATIAL: phaseDirectory = "03_spatial"; break;
		default: return {};
	}

	return workspace / phaseDirectory;
}
