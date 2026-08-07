#pragma once

#include <SDL.h>

#include <filesystem>
#include <memory>
#include <optional>

#include "editor/backend/BackendClient.h"
#include "editor/controller/PipelineController.h"
#include "editor/persistence/RunStore.h"
#include "editor/ui/UIManager.h"

class Scene;

class App {
public:
    explicit App(std::unique_ptr<BackendClient> backendClient, std::filesystem::path runsDirectory);
    ~App();

    bool Initialize();
    void Run();

private:
    void Shutdown();
    void SynchronizeScene();
    void HandleViewportInput(const SDL_Event& event);

    bool InitializeSDL();
    bool InitializeOpenGL();

    std::unique_ptr<BackendClient> backendClient_;
    RunStore runStore_;
    PipelineController controller_;
    bool running_ = false;
    bool sdlInitialized_ = false;
    UIManager uiManager_;
    std::unique_ptr<Scene> scene_;
    std::optional<RunId> displayedRunId_;
    SDL_Window* window_ = nullptr;
    SDL_GLContext glContext_ = nullptr;
};
