#pragma once

#include <SDL.h>

#include <memory>

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

    bool InitializeSDL();
    bool InitializeOpenGL();
    bool InitializeImGui();


    bool running_ = false;
    bool sdlInitialized_ = false;
    bool imguiSdlInitialized_ = false;
    bool imguiOpenGLInitialized_ = false;
    UIManager uiManager_;
    std::unique_ptr<Scene> scene_;
    SDL_Window* window_ = nullptr;
    SDL_GLContext glContext_ = nullptr;
};
