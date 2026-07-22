#include "App.h"

#include <iostream>
#include <string_view>
#include <utility>

#include "BackendLaunchConfig.h"

namespace {

void PrintUsage() {
	std::cout << "Usage: AnitoScan [--backend=production|dummy]" << std::endl;
}

} // namespace

int main(int argc, char** argv) {
	BackendKind backendKind = DefaultBackendKind();
	constexpr std::string_view backendPrefix = "--backend=";

	for (int index = 1; index < argc; ++index) {
		const std::string_view argument(argv[index]);
		if (argument == "--help" || argument == "-h") {
			PrintUsage();
			return 0;
		}
		if (!argument.starts_with(backendPrefix)) {
			std::cerr << "Unknown argument: " << argument << std::endl;
			PrintUsage();
			return 2;
		}

		const auto parsedKind = ParseBackendKind(argument.substr(backendPrefix.size()));
		if (!parsedKind) {
			std::cerr << "Unknown backend: " << argument.substr(backendPrefix.size()) << std::endl;
			PrintUsage();
			return 2;
		}
		backendKind = *parsedKind;
	}

	std::string error;
	auto backendConfig = ResolveBackendLaunchConfig(backendKind, PROJECT_ROOT_DIR, error);
	if (!backendConfig) {
		std::cerr << "[ERROR]: " << error << std::endl;
		return 2;
	}

	App app(1920, 1080, std::move(*backendConfig));
	if (!app.Initialize()) {
		return 1;
	}
	app.Run();
	return 0;
}
