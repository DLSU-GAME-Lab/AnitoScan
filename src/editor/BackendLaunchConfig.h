#pragma once

#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

enum class BackendKind {
	Production,
	Dummy,
};

struct BackendLaunchConfig {
	BackendKind kind;
	std::string displayName;
	std::string executable;
	std::vector<std::string> arguments;
};

BackendKind DefaultBackendKind();
std::optional<BackendKind> ParseBackendKind(std::string_view value);
std::string_view BackendKindName(BackendKind kind);
std::optional<BackendLaunchConfig> ResolveBackendLaunchConfig(
	BackendKind kind,
	const std::filesystem::path& projectRoot,
	std::string& error);
