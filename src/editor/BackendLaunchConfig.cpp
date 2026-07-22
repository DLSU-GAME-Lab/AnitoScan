#include "BackendLaunchConfig.h"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <iterator>

namespace {

std::optional<std::string> ReadPythonVersion(
	const std::filesystem::path& projectRoot,
	std::string& error) {
	const std::filesystem::path versionPath = projectRoot / ".python-version";
	std::ifstream input(versionPath);
	if (!input) {
		error = "Unable to read Python version file: " + versionPath.string();
		return std::nullopt;
	}

	std::string version(
		(std::istreambuf_iterator<char>(input)),
		std::istreambuf_iterator<char>());
	version.erase(
		std::remove_if(version.begin(), version.end(), [](unsigned char character) {
			return std::isspace(character) != 0;
		}),
		version.end());
	if (version.empty()) {
		error = "Python version file is empty: " + versionPath.string();
		return std::nullopt;
	}
	return version;
}

} // namespace

BackendKind DefaultBackendKind() {
#if defined(_WIN32)
	return BackendKind::Production;
#else
	return BackendKind::Dummy;
#endif
}

std::optional<BackendKind> ParseBackendKind(std::string_view value) {
	if (value == "production") return BackendKind::Production;
	if (value == "dummy") return BackendKind::Dummy;
	return std::nullopt;
}

std::string_view BackendKindName(BackendKind kind) {
	switch (kind) {
	case BackendKind::Production:
		return "production";
	case BackendKind::Dummy:
		return "dummy";
	}
	return "unknown";
}

std::optional<BackendLaunchConfig> ResolveBackendLaunchConfig(
	BackendKind kind,
	const std::filesystem::path& projectRoot,
	std::string& error) {
	const std::filesystem::path coreDirectory = projectRoot / "src" / "pipeline" / "core";

	if (kind == BackendKind::Production) {
#if !defined(_WIN32)
		error = "The production backend is supported only on Windows. Use --backend=dummy on this platform.";
		return std::nullopt;
#else
		return BackendLaunchConfig{
			.kind = kind,
			.displayName = "production",
			.executable = UV_EXECUTABLE_PATH,
			.arguments = {
				"run",
				"--project",
				projectRoot.string(),
				"python",
				(coreDirectory / "backend.py").string(),
				"--ipc",
			},
		};
#endif
	}

	const std::optional<std::string> pythonVersion = ReadPythonVersion(projectRoot, error);
	if (!pythonVersion) return std::nullopt;

	return BackendLaunchConfig{
		.kind = kind,
		.displayName = "dummy",
		.executable = UV_EXECUTABLE_PATH,
		.arguments = {
			"run",
			"--isolated",
			"--no-project",
			"--python",
			*pythonVersion,
			"--",
			"python",
			"-u",
			(coreDirectory / "dummy.py").string(),
			"--ipc",
		},
	};
}
