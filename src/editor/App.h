#pragma once

#include <SDL.h>

#include <memory>
#include <optional>

#include "editor/controller/PipelineController.h"
#include "editor/ui/UIManager.h"

class Scene;

class App {
public:
    App();
    ~App();

    bool Initialize();
    void Run();

private:
    void Shutdown();
    void SynchronizeScene();

    bool InitializeSDL();
    bool InitializeOpenGL();

    bool running_ = false;
    bool sdlInitialized_ = false;
    PipelineController controller_;
    UIManager uiManager_;
    std::unique_ptr<Scene> scene_;
    std::optional<RunId> displayedRunId_;
    SDL_Window* window_ = nullptr;
    SDL_GLContext glContext_ = nullptr;
};
