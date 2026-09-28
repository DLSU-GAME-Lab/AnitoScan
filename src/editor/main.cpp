#include "App.h"

#include "editor/backend/BackendClient.h"
#include "editor/backend/BackendConfig.h"

#include <filesystem>
#include <iostream>
#include <optional>
#include <string_view>
#include <utility>
#include <memory>

// TODO: Move argument parsing and AppConfig out of main.cpp into a dedicated 'cli' module
// when new application flags (--mode, --log-level) are added. Remove BackendConfig.h include
// from main.cpp when extracted. The current hand-rolled logic is strictly positional; switch
// to a flexible token loop or library parser when extracting.
namespace {
    constexpr const char* kDummyScriptPath = "src/pipeline/core/dummy.py";
    constexpr const char* kPipelineScriptPath = "src/pipeline/core/pipeline.py";

    struct AppConfig {
        BackendConfig backendConfig;
        std::filesystem::path runsDirectory;
        // Future additions:
        // WindowConfig windowConfig;
        // LogConfig logConfig;
    };

    std::optional<AppConfig> ParseCliArgs(int argc, char** argv) {
        std::string_view backend = "dummy";
        if (argc != 1) {
            const std::string_view arg1 = (argc >= 2) ? argv[1] : "";
            if (argc == 2 && arg1 == "--backend") {
                std::cerr << "Missing value for --backend (expected 'dummy' or 'pipeline')\n";
                return std::nullopt;
            }
            if (argc != 3 || arg1 != "--backend") {
                std::cerr << "Unknown option. Usage: " << argv[0]
                          << " [--backend <dummy|pipeline>]\n";
                return std::nullopt;
            }

            backend = argv[2];
            if (backend != "dummy" && backend != "pipeline") {
                std::cerr << "Unknown backend '" << backend
                          << "' (expected 'dummy' or 'pipeline')\n";
                return std::nullopt;
            }
        }

        BackendConfig backendConfig{
            .executable = "uv",
            .arguments = {"run", "--no-project", "python", kDummyScriptPath},
            .workingDirectory = std::filesystem::path(PROJECT_ROOT_DIR),
        };
        if (backend == "pipeline") {
            backendConfig.arguments = {"run", "python", kPipelineScriptPath, "--ipc"};
        }

        return AppConfig{
            .backendConfig = std::move(backendConfig),
            .runsDirectory = std::filesystem::path(PROJECT_ROOT_DIR) / "data" / "runs",
        };
    }
} // namespace

int main(int argc, char** argv) {
    auto appConfig = ParseCliArgs(argc, argv);
    if (!appConfig) {
        return 2;
    }

    auto backendClient = std::make_unique<BackendClient>(std::move(appConfig->backendConfig));

    App app(std::move(backendClient), appConfig->runsDirectory);
    if (!app.Initialize()) {
        return 1;
    }

    app.Run();
    return 0;
}
