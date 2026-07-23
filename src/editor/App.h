#pragma once

#include <iostream>

#include <glad/gl.h>
#include <SDL.h>
#include <SDL_opengl.h>
#include <backends/imgui_impl_sdl2.h>
#include <backends/imgui_impl_opengl3.h>

#include "Types.h"
#include "BackendLaunchConfig.h"
#include "render/Scene.h"
#include "IPCClient.h"
#include "state/EditorState.h"
#include "controller/PipelineController.h"

class IPCClient;

class App {
public:
    App(int width, int height, BackendLaunchConfig backendConfig);
    ~App();

    bool Initialize();
    void Run();

private:
    bool InitializeSDL();
    bool InitializeOpenGL();
    void ProcessMouseEvents(SDL_Event event);
    void ProcessKeyboardEvents(SDL_Event event);
    void Cleanup();

private:
    bool isRunning;
    SDL_Window* window;
    SDL_GLContext glContext;

    int screenWidth;
    int screenHeight;

    BackendLaunchConfig backendConfig;
    IPCClient ipc;
    EditorState state;
    std::unique_ptr<PipelineController> controller;
    std::unique_ptr<Scene> scene;

    bool mouseDragging = false;
    bool middleMousehold = false;
    Uint64 lastTime = 0;
    float deltaTime;
};
