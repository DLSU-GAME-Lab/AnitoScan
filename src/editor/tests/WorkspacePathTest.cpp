#include <filesystem>
#include <iostream>

#include "../WorkspacePath.h"

namespace {

bool ExpectEqual(
	const std::filesystem::path& actual,
	const std::filesystem::path& expected,
	const char* description) {
	if (actual == expected) {
		return true;
	}

	std::cerr << description << ": expected " << expected
	          << ", got " << actual << std::endl;
	return false;
}

} // namespace

int main() {
	const std::filesystem::path workspace =
		std::filesystem::path("exact") / "backend" / "workspace";

	bool passed = true;
	passed &= ExpectEqual(
		WorkspacePathForPhase(workspace, Phase::CAPTURE),
		workspace / "01_capture",
		"Capture workspace path");
	passed &= ExpectEqual(
		WorkspacePathForPhase(workspace, Phase::MASKING),
		workspace / "02_masking",
		"Masking workspace path");
	passed &= ExpectEqual(
		WorkspacePathForPhase(workspace, Phase::SPATIAL),
		workspace / "03_spatial",
		"Spatial workspace path");
	passed &= ExpectEqual(
		WorkspacePathForPhase(workspace, Phase::GEOMETRY),
		{},
		"Unsupported phase path");

	return passed ? 0 : 1;
}
