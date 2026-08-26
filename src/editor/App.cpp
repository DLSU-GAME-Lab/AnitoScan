#include "App.h"

#include "editor/backend/BackendClient.h"
#include "editor/protocol/BackendProtocol.h"
#include "render/Scene.h"

#include <iostream>
#include <memory>
#include <utility>
#include <vector>

#include <glad/gl.h>

namespace {
constexpr int kInitialWindowWidth = 1280;
constexpr int kInitialWindowHeight = 720;

const char* PipelineModeText(int value) {
    return value == 1 ? "pipe" : "disk";
}

const char* CaptureModeText(int value) {
    switch (value) {
    case 1:
        return "image";
    case 2:
        return "video";
    default:
        return "auto";
    }
}

const char* QualityText(int value) {
    switch (value) {
    case 1:
        return "medium";
    case 2:
        return "detailed";
    default:
        return "fast";
    }
}

const char* ModelSizeText(int value) {
    constexpr const char* sizes[] = {"n", "s", "m", "l", "x"};
    return value >= 0 && value < 5 ? sizes[value] : "s";
}

StoredRun ToStoredRun(const RunState& run) {
    return {
        run.id, run.name, run.status, run.config.inputSource, run.config.mode,
        run.config.captureMode, run.config.quality, run.config.force,
        run.config.iouThreshold, run.config.minimumFrames, run.config.driftLimit,
        run.config.yoloModelSize, run.outputModelPath
    };
}

RunState ToRunState(const StoredRun& run) {
    RunState result;
    result.id = run.id;
    result.name = run.name;
    result.status = run.status;
    result.outputModelPath = run.outputModelPath;
    result.config.inputSource = run.inputSource;
    result.config.mode = run.mode;
    result.config.captureMode = run.captureMode;
    result.config.quality = run.quality;
    result.config.force = run.force;
    result.config.iouThreshold = run.iouThreshold;
    result.config.minimumFrames = run.minimumFrames;
    result.config.driftLimit = run.driftLimit;
    result.config.yoloModelSize = run.yoloModelSize;
    return result;
}

std::vector<std::string> Split(const std::string& value) {
    std::vector<std::string> parts;
    std::size_t start = 0;
    while (start <= value.size()) {
        const std::size_t end = value.find('\n', start);
        parts.push_back(value.substr(start, end - start));
        if (end == std::string::npos) break;
        start = end + 1;
    }
    return parts;
}
}

App::App(std::unique_ptr<BackendClient> backendClient, std::filesystem::path runsDirectory)
    : backendClient_(std::move(backendClient)), runStore_(std::move(runsDirectory)) {}

App::~App() { Shutdown(); }

bool App::Initialize() {
    if (!InitializeSDL() || !InitializeOpenGL() || !uiManager_.Initialize(window_, glContext_)) {
        Shutdown();
        return false;
    }
    controller_.emplace();
    std::vector<RunSummary> summaries;
    for (const StoredRun& run : runStore_.LoadRuns()) {
        summaries.push_back({run.id, run.name, run.status});
    }
    controller_->RestoreRuns(std::move(summaries));
    scene_ = std::make_unique<Scene>();
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
    window_ = SDL_CreateWindow("AnitoScan", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        kInitialWindowWidth, kInitialWindowHeight,
        SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI);
    if (!window_) {
        std::cerr << "Window creation failed: " << SDL_GetError() << '\n';
        return false;
    }
    return true;
}

bool App::InitializeOpenGL() {
    glContext_ = SDL_GL_CreateContext(window_);
    if (!glContext_ || SDL_GL_MakeCurrent(window_, glContext_) != 0 ||
        !gladLoadGL(reinterpret_cast<GLADloadfunc>(SDL_GL_GetProcAddress))) {
        std::cerr << "OpenGL initialization failed: " << SDL_GetError() << '\n';
        return false;
    }
    SDL_GL_SetSwapInterval(1);
    return true;
}

void App::Run() {
    while (running_) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            uiManager_.ProcessEvent(event);
            HandleViewportInput(event);
            if (event.type == SDL_QUIT || (event.type == SDL_WINDOWEVENT && event.window.event == SDL_WINDOWEVENT_CLOSE)) running_ = false;
        }

        for (const std::string& raw : backendClient_->PollMessages()) {
            if (const auto message = ParseMessage(raw)) {
                controller_->HandleBackendInput({message->type, message->value});
            }
        }
        for (const std::string& diagnostic : backendClient_->PollDiagnostics()) {
            std::cerr << "[backend] " << diagnostic << '\n';
        }
        if (backendClient_->ConsumeDisconnect()) {
            controller_->HandleBackendInput({"backend_disconnected", {}});
        }

        ProcessPersistenceRequests();
        SynchronizeScene();
        if (scene_->GetModel()) {
            scene_->Render(
                uiManager_.GetViewportWidth(),
                uiManager_.GetViewportHeight()
            );
        }
        if (uiManager_.ConsumeRecenterRequest() && scene_->GetModel()) {
            scene_->Recenter();
        }

        const RunState* run = controller_->GetActiveRun();
        if (!run) {
            RunSetupData data;
            data.canCreateRun = controller_->CanCreateRun();
            if (!data.canCreateRun) {
                data.message = "Backend unavailable";
            }
            for (const RunSummary& summary : controller_->GetRunSummaries()) {
                data.runIds.push_back(summary.id);
                data.runNames.push_back(summary.name);
                data.runStatuses.push_back(summary.status);
            }
            uiManager_.SwitchScreen(UIScreen::RunSetup);
            uiManager_.SetRunSetupData(std::move(data));
        } else if (const PhaseNavigationData navigation = controller_->GetPhaseNavigationData();
            run->status == "completed" && navigation.viewingLatest) {
            uiManager_.SwitchScreen(UIScreen::PostExport);
            uiManager_.SetPostExportData({
                run->name,
                run->status,
                navigation,
                scene_->GetModel() ? scene_->GetColorTexture() : 0
            });
        } else {
            uiManager_.SwitchScreen(UIScreen::Phase);
            uiManager_.SetPhaseData(controller_->GetPhaseDisplayData());
        }

        uiManager_.BeginFrame();
        uiManager_.Render();
        for (const UIInput& input : uiManager_.PollInputs()) {
            if (input.click == UIClick::StartRun) controller_->StartRun(input.value);
            else if (input.click == UIClick::CancelRun) controller_->CancelRun(input.value);
            else if (input.click == UIClick::DeleteRun) controller_->DeleteRun(input.value);
            else if (input.click == UIClick::SelectRun) controller_->SelectRun(input.value);
            else if (input.click == UIClick::SubmitSelection && run) controller_->SubmitSelection(run->id, input.value);
            else if (input.click == UIClick::NewRun) controller_->ClearActiveRun();
            else if (input.click == UIClick::PreviousPhase) controller_->ViewPreviousPhase();
            else if (input.click == UIClick::NextPhase) controller_->ViewNextPhase();
            else if (input.click == UIClick::FollowLive) controller_->FollowLivePhase();
            else if (input.click == UIClick::CreateRun) {
                const auto values = Split(input.value);
                if (values.size() >= 10) {
                    RunConfig config;
                    config.inputSource = values[1];
                    config.minimumFrames = std::stoi(values[2]);
                    config.mode = PipelineModeText(std::stoi(values[3]));
                    config.captureMode = CaptureModeText(std::stoi(values[4]));
                    config.quality = QualityText(std::stoi(values[5]));
                    config.iouThreshold = std::stof(values[6]);
                    config.driftLimit = std::stoi(values[7]);
                    config.yoloModelSize = ModelSizeText(std::stoi(values[8]));
                    config.force = values[9] == "1";
                    controller_->CreateRun(values[0], std::move(config));
                }
            }
        }
        ProcessPersistenceRequests();
        for (const PipelineMessage& message : controller_->PollMessages()) {
            const std::string json = SerializeMessage(message.type, message.value);
            if (!json.empty()) backendClient_->Send(json);
        }

        int width = 0, height = 0;
        SDL_GL_GetDrawableSize(window_, &width, &height);
        glViewport(0, 0, width, height);
        glClearColor(0.08f, 0.08f, 0.10f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        uiManager_.EndFrame();
        SDL_GL_SwapWindow(window_);
    }
}

void App::HandleViewportInput(const SDL_Event& event) {
    if (!uiManager_.IsViewportHovered() || !scene_->GetModel()) return;
    if (event.type == SDL_MOUSEMOTION) {
        if ((event.motion.state & SDL_BUTTON_LMASK) != 0) scene_->Orbit(static_cast<float>(event.motion.xrel), static_cast<float>(event.motion.yrel));
        else if ((event.motion.state & (SDL_BUTTON_MMASK | SDL_BUTTON_RMASK)) != 0) scene_->Pan(static_cast<float>(event.motion.xrel), static_cast<float>(event.motion.yrel));
    } else if (event.type == SDL_MOUSEWHEEL) scene_->Zoom(static_cast<float>(event.wheel.y));
}

void App::ProcessPersistenceRequests() {
    for (const PersistenceRequest& request : controller_->PollPersistenceRequests()) {
        if (request.type == "save") {
            if (const RunState* run = controller_->GetActiveRun(); run && run->id == request.runId) {
                runStore_.SaveRun(ToStoredRun(*run));
            }
        } else if (request.type == "load") {
            StoredRun run;
            if (runStore_.LoadRun(request.runId, run)) {
                controller_->LoadRun(ToRunState(run));
            }
        } else if (request.type == "delete") {
            runStore_.DeleteRun(request.runId);
        }
    }
}

void App::SynchronizeScene() {
    const RunState* run = controller_->GetActiveRun();
    if (!run || run->status != "completed" || run->outputModelPath.empty()) {
        if (displayedRunId_) { scene_->ClearModel(); displayedRunId_.reset(); }
        return;
    }
    if (displayedRunId_ != run->id) { scene_->LoadModel(run->outputModelPath); displayedRunId_ = run->id; }
}

void App::Shutdown() {
    running_ = false;
    if (controller_) {
        controller_->PrepareForShutdown();
        ProcessPersistenceRequests();
    }
    backendClient_->Stop();
    scene_.reset();
    controller_.reset();
    uiManager_.Shutdown();
    if (glContext_) { SDL_GL_DeleteContext(glContext_); glContext_ = nullptr; }
    if (window_) { SDL_DestroyWindow(window_); window_ = nullptr; }
    if (sdlInitialized_) { SDL_Quit(); sdlInitialized_ = false; }
}
