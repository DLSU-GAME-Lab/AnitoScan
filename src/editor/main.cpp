#include "App.h"

#include "editor/backend/BackendConfig.h"

#include <filesystem>
#include <iostream>
#include <string_view>
#include <utility>

int main(int argc, char** argv) {
    if (argc != 1) {
        if (argc == 2 && std::string_view(argv[1]) == "--backend") {
            std::cerr << "Missing value for --backend (expected 'dummy')\n";
            return 2;
        }
        if (argc == 3 && std::string_view(argv[1]) == "--backend") {
            const std::string_view backend = argv[2];
            if (backend == "pipeline") {
                std::cerr << "Backend 'pipeline' is not supported by the current protocol\n";
                return 2;
            }
            if (backend != "dummy") {
                std::cerr << "Unknown backend '" << backend << "' (expected 'dummy')\n";
                return 2;
            }
        } else {
            std::cerr << "Unknown option. Usage: " << argv[0] << " [--backend dummy]\n";
            return 2;
        }
    }

    BackendConfig backendConfig{
        .executable = "uv",
        .arguments = {"run", "--no-project", "python", "src/pipeline/core/dummy.py"},
        .workingDirectory = std::filesystem::path(PROJECT_ROOT_DIR),
        .runsDirectory = std::filesystem::path(PROJECT_ROOT_DIR) / "data" / "runs" / "dummy",
    };

    App app(std::move(backendConfig));
    if (!app.Initialize()) {
        return 1;
    }

    app.Run();
    return 0;
}
