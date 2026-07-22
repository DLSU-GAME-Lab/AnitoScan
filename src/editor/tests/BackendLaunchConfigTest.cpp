#include "../BackendLaunchConfig.h"

#include <algorithm>
#include <filesystem>
#include <iostream>
#include <string>

namespace {

bool Contains(const std::vector<std::string>& values, const std::string& expected) {
	return std::find(values.begin(), values.end(), expected) != values.end();
}

bool ContainsPathEnding(const std::vector<std::string>& values, const std::string& filename) {
	return std::any_of(values.begin(), values.end(), [&](const std::string& value) {
		return std::filesystem::path(value).filename() == filename;
	});
}

} // namespace

int main() {
#if defined(_WIN32)
	if (DefaultBackendKind() != BackendKind::Production) {
		std::cerr << "Windows must default to the production backend" << std::endl;
		return 1;
	}
#else
	if (DefaultBackendKind() != BackendKind::Dummy) {
		std::cerr << "Non-Windows platforms must default to the dummy backend" << std::endl;
		return 1;
	}
#endif

	std::string error;
	const auto dummy = ResolveBackendLaunchConfig(BackendKind::Dummy, PROJECT_ROOT_DIR, error);
	if (!dummy) {
		std::cerr << error << std::endl;
		return 1;
	}
	if (std::filesystem::path(dummy->executable).stem() != "uv" ||
		!Contains(dummy->arguments, "--isolated") ||
		!Contains(dummy->arguments, "--no-project") ||
		!ContainsPathEnding(dummy->arguments, "dummy.py") ||
		ContainsPathEnding(dummy->arguments, "pipeline.py")) {
		std::cerr << "Dummy launch command is not isolated from the production project" << std::endl;
		return 1;
	}

#if !defined(_WIN32)
	error.clear();
	if (ResolveBackendLaunchConfig(BackendKind::Production, PROJECT_ROOT_DIR, error)) {
		std::cerr << "Production backend must be rejected outside Windows" << std::endl;
		return 1;
	}
	if (error.empty()) {
		std::cerr << "Unsupported production mode must return an actionable error" << std::endl;
		return 1;
	}
#endif

	std::cout << "Backend launch configuration test passed" << std::endl;
	return 0;
}
