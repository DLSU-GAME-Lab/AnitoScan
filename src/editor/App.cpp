#include "App.h"

#include "render/Scene.h"

#include <iostream>
#include <memory>
#include <utility>

#include <glad/gl.h>

namespace {
    constexpr int kInitialWindowWidth = 1280;
    constexpr int kInitialWindowHeight = 720;
}

App::App(std::unique_ptr<BackendClient> backendClient, std::filesystem::path runsDirectory)
    : backendClient_(std::move(backendClient)),
      runStore_(runsDirectory),
      controller_(*backendClient_, runStore_) {}

App::~App() {
    Shutdown();
}

bool App::Initialize() {
    if (!InitializeSDL() || !InitializeOpenGL() || !uiManager_.Initialize(window_, glContext_)) {
        Shutdown();
        return false;
    }

    scene_ = std::make_unique<Scene>();
    controller_.RestoreRuns(runStore_.LoadRuns());
    if (!backendClient_->Start()) {
        std::cerr << "Failed to start backend\n";
        Shutdown();
        return false;
    }

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

void App::Run() {
    while (running_) {
        // Forward input events to the UI and handle application exit requests.
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            uiManager_.ProcessEvent(event);
            HandleViewportInput(event);
            if (event.type == SDL_QUIT ||
                (event.type == SDL_WINDOWEVENT && event.window.event == SDL_WINDOWEVENT_CLOSE)) {
                running_ = false;
            }
        }

        for (const BackendEvent& backendEvent : backendClient_->PollEvents()) {
            controller_.HandleEvent(backendEvent);
        }
        for (const std::string& diagnostic : backendClient_->PollDiagnostics()) {
            std::cerr << "[backend] " << diagnostic << '\n';
            controller_.AddLog("[diagnostic] " + diagnostic);
        }

        SynchronizeScene();
        if (uiManager_.ConsumeRecenterRequest() && scene_->GetModel()) {
            scene_->Recenter();
        }

        // Render the scene offscreen at the current UI viewport size.
        const int viewportWidth = uiManager_.GetViewportWidth();
        const int viewportHeight = uiManager_.GetViewportHeight();
        if (scene_->GetModel() && viewportWidth > 0 && viewportHeight > 0) {
            scene_->Render(viewportWidth, viewportHeight);
        }

        // Build the UI frame with the offscreen scene texture.
        uiManager_.BeginFrame();
        uiManager_.Render(
            controller_.GetState(),
            controller_,
            scene_->GetModel() ? scene_->GetColorTexture() : 0
        );

        // Clear the application framebuffer and draw the completed UI frame.
        int width = 0;
        int height = 0;
        SDL_GL_GetDrawableSize(window_, &width, &height);
        glViewport(0, 0, width, height);
        glClearColor(0.08f, 0.08f, 0.10f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        uiManager_.EndFrame();

        // Present the completed frame to the window.
        SDL_GL_SwapWindow(window_);
    }
}

void App::HandleViewportInput(const SDL_Event& event) {
    if (!uiManager_.IsViewportHovered() || !scene_->GetModel()) {
        return;
    }

    if (event.type == SDL_MOUSEMOTION) {
        if ((event.motion.state & SDL_BUTTON_LMASK) != 0) {
            scene_->Orbit(
                static_cast<float>(event.motion.xrel),
                static_cast<float>(event.motion.yrel)
            );
        } else if (
            (event.motion.state & SDL_BUTTON_MMASK) != 0 ||
            (event.motion.state & SDL_BUTTON_RMASK) != 0
        ) {
            scene_->Pan(
                static_cast<float>(event.motion.xrel),
                static_cast<float>(event.motion.yrel)
            );
        }
    } else if (event.type == SDL_MOUSEWHEEL) {
        scene_->Zoom(static_cast<float>(event.wheel.y));
    }
}

void App::SynchronizeScene() {
    const RunState* selectedRun = controller_.GetSelectedRun();
    const bool isDisplayable = selectedRun != nullptr &&
        selectedRun->status == RunStatus::Completed && selectedRun->outputModelPath.has_value();

    if (!isDisplayable) {
        if (displayedRunId_) {
            scene_->ClearModel();
            displayedRunId_.reset();
        }
        return;
    }

    if (displayedRunId_ != selectedRun->id) {
        scene_->LoadModel(selectedRun->outputModelPath->string());
        displayedRunId_ = selectedRun->id;
    }
}

void App::Shutdown() {
    running_ = false;
    displayedRunId_.reset();
    if (backendClient_) {
        backendClient_->Stop();
    }
    scene_.reset();

    uiManager_.Shutdown();

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
