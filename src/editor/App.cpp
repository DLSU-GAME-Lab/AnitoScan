#include "App.h"

#include "render/Scene.h"

#include <iostream>
#include <memory>

#include <glad/gl.h>
#include <imgui.h>
#include <backends/imgui_impl_opengl3.h>
#include <backends/imgui_impl_sdl2.h>

namespace {
    constexpr int kInitialWindowWidth = 1280;
    constexpr int kInitialWindowHeight = 720;
}

App::App() = default;

App::~App() {
    Shutdown();
}

bool App::Initialize() {
    if (!InitializeSDL() || !InitializeOpenGL() || !InitializeImGui()) {
        Shutdown();
        return false;
    }

    scene_ = std::make_unique<Scene>();
    running_ = true;
    return true;
}

bool App::InitializeSDL() {
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) != 0) {
        std::cerr << "SDL initialization failed: " << SDL_GetError() << '\n';
        return false;
    }
    sdlInitialized_ = true;

    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
#ifdef __APPLE__
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_FLAGS, SDL_GL_CONTEXT_FORWARD_COMPATIBLE_FLAG);
#endif
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24);

    window_ = SDL_CreateWindow(
        "AnitoScan",
        SDL_WINDOWPOS_CENTERED,
        SDL_WINDOWPOS_CENTERED,
        kInitialWindowWidth,
        kInitialWindowHeight,
        SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI
    );

    if (!window_) {
        std::cerr << "Window creation failed: " << SDL_GetError() << '\n';
        return false;
    }

    return true;
}

bool App::InitializeOpenGL() {
    glContext_ = SDL_GL_CreateContext(window_);
    if (!glContext_) {
        std::cerr << "OpenGL context creation failed: " << SDL_GetError() << '\n';
        return false;
    }

    if (SDL_GL_MakeCurrent(window_, glContext_) != 0) {
        std::cerr << "Activating OpenGL context failed: " << SDL_GetError() << '\n';
        return false;
    }

    if (!gladLoadGL(reinterpret_cast<GLADloadfunc>(SDL_GL_GetProcAddress))) {
        std::cerr << "GLAD initialization failed\n";
        return false;
    }

    if (SDL_GL_SetSwapInterval(1) != 0) {
        std::cerr << "Failed to enable VSync: " << SDL_GetError() << '\n';
    }
    return true;
}

bool App::InitializeImGui() {
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGui::StyleColorsDark();

    if (!ImGui_ImplSDL2_InitForOpenGL(window_, glContext_)) {
        std::cerr << "ImGui SDL2 backend initialization failed\n";
        return false;
    }
    imguiSdlInitialized_ = true;

    if (!ImGui_ImplOpenGL3_Init("#version 330")) {
        std::cerr << "ImGui OpenGL backend initialization failed\n";
        return false;
    }
    imguiOpenGLInitialized_ = true;

    return true;
}

void App::Run() {
    while (running_) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            ImGui_ImplSDL2_ProcessEvent(&event);
            if (event.type == SDL_QUIT ||
                (event.type == SDL_WINDOWEVENT && event.window.event == SDL_WINDOWEVENT_CLOSE)) {
                running_ = false;
            }
        }

        const int viewportWidth = uiManager_.GetViewportWidth();
        const int viewportHeight = uiManager_.GetViewportHeight();
        if (scene_ && viewportWidth > 0 && viewportHeight > 0) {
            scene_->Render(viewportWidth, viewportHeight);
        }

        ImGui_ImplOpenGL3_NewFrame();
        ImGui_ImplSDL2_NewFrame();
        ImGui::NewFrame();

        uiManager_.Render(scene_ ? scene_->GetColorTexture() : 0);

        ImGui::Render();

        int width = 0;
        int height = 0;
        SDL_GL_GetDrawableSize(window_, &width, &height);
        glViewport(0, 0, width, height);
        glClearColor(0.08f, 0.08f, 0.10f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());

        SDL_GL_SwapWindow(window_);
    }
}

void App::Shutdown() {
    running_ = false;
    scene_.reset();

    if (imguiOpenGLInitialized_) {
        ImGui_ImplOpenGL3_Shutdown();
        imguiOpenGLInitialized_ = false;
    }
    if (imguiSdlInitialized_) {
        ImGui_ImplSDL2_Shutdown();
        imguiSdlInitialized_ = false;
    }
    if (ImGui::GetCurrentContext()) {
        ImGui::DestroyContext();
    }
    if (glContext_) {
        SDL_GL_DeleteContext(glContext_);
        glContext_ = nullptr;
    }
    if (window_) {
        SDL_DestroyWindow(window_);
        window_ = nullptr;
    }
    if (sdlInitialized_) {
        SDL_Quit();
        sdlInitialized_ = false;
    }
}
