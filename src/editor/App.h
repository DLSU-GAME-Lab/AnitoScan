#pragma once

#include <SDL.h>

#include <memory>
#include <optional>

#include "editor/backend/BackendClient.h"
#include "editor/backend/BackendConfig.h"
#include "editor/controller/PipelineController.h"
#include "editor/ui/UIManager.h"

class Scene;

class App {
public:
    explicit App(BackendConfig backendConfig);
    ~App();

    bool Initialize();
    void Run();

private:
    void Shutdown();
    void SynchronizeScene();

    bool InitializeSDL();
    bool InitializeOpenGL();

    BackendConfig backendConfig_;
    BackendClient backendClient_;
    PipelineController controller_;
    bool running_ = false;
    bool sdlInitialized_ = false;
    UIManager uiManager_;
    std::unique_ptr<Scene> scene_;
    std::optional<RunId> displayedRunId_;
    SDL_Window* window_ = nullptr;
    SDL_GLContext glContext_ = nullptr;
};
