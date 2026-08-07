#include "App.h"

#include "editor/backend/BackendConfig.h"

#include <filesystem>
#include <iostream>
#include <optional>
#include <string_view>
#include <utility>

// TODO: Move argument parsing to a dedicated 'CLI' or 'BackendConfig::FromArgs' (ideally CLI)
// module once real backend options (--backend pipeline) or new flags (--mode, --log-level)
// are added. Remove BackendConfig.h include and other includes from main.cpp when extracted.
// The current hand-rolled logic is strictly positional, switch to a flexible token loop or
// library parser when extracting.
namespace {
    std::optional<BackendConfig> ParseCliArgs(int argc, char** argv) {
        if (argc != 1) {
            if (argc == 2 && std::string_view(argv[1]) == "--backend") {
                std::cerr << "Missing value for --backend (expected 'dummy')\n";
                return std::nullopt;
            }
            if (argc == 3 && std::string_view(argv[1]) == "--backend") {
                const std::string_view backend = argv[2];
                if (backend == "pipeline") {
                    std::cerr << "Backend 'pipeline' is not supported by the current protocol\n";
                    return std::nullopt;
                }
                if (backend != "dummy") {
                    std::cerr << "Unknown backend '" << backend << "' (expected 'dummy')\n";
                    return std::nullopt;
                }
            } else {
                std::cerr << "Unknown option. Usage: " << argv[0] << " [--backend dummy]\n";
                return std::nullopt;
            }
        }

        return BackendConfig{
            .executable = "uv",
            .arguments = {"run", "--no-project", "python", "src/pipeline/core/dummy.py"},
            .workingDirectory = std::filesystem::path(PROJECT_ROOT_DIR),
            .runsDirectory = std::filesystem::path(PROJECT_ROOT_DIR) / "data" / "runs" / "dummy",
        };
    }
} // namespace

int main(int argc, char** argv) {
    auto backendConfig = ParseCliArgs(argc, argv);
    if (!backendConfig) {
        return 2;
    }

    App app(std::move(*backendConfig));
    if (!app.Initialize()) {
        return 1;
    }

    app.Run();
    return 0;
}
