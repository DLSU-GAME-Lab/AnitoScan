#include "editor/ui/UIManager.h"

#include "editor/controller/PipelineController.h"
#include "editor/domain/EditorState.h"

#include <iostream>

#include <imgui.h>
#include <backends/imgui_impl_opengl3.h>
#include <backends/imgui_impl_sdl2.h>

namespace {
const RunState* FindSelectedRun(const EditorState& state) {
    if (!state.selectedRunId) {
        return nullptr;
    }

    for (const RunState& run : state.runs) {
        if (run.id == *state.selectedRunId) {
            return &run;
        }
    }

    return nullptr;
}
}

UIManager::~UIManager() {
    Shutdown();
}

bool UIManager::Initialize(SDL_Window* window, SDL_GLContext glContext) {
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    contextCreated_ = true;
    ImGui::StyleColorsDark();

    if (!ImGui_ImplSDL2_InitForOpenGL(window, glContext)) {
        std::cerr << "ImGui SDL2 backend initialization failed\n";
        Shutdown();
        return false;
    }
    sdlBackendInitialized_ = true;

    if (!ImGui_ImplOpenGL3_Init("#version 330")) {
        std::cerr << "ImGui OpenGL backend initialization failed\n";
        Shutdown();
        return false;
    }
    openGLBackendInitialized_ = true;

    return true;
}

void UIManager::ProcessEvent(const SDL_Event& event) {
    ImGui_ImplSDL2_ProcessEvent(&event);
}

void UIManager::BeginFrame() {
    ImGui_ImplOpenGL3_NewFrame();
    ImGui_ImplSDL2_NewFrame();
    ImGui::NewFrame();
}

void UIManager::Render(
    const EditorState& state,
    PipelineController& controller,
    unsigned int textureId
) {
    const RunState* selectedRun = FindSelectedRun(state);
    if (selectedRun == nullptr) {
        runSetupScreen_.Render(state, controller);
    } else if (
        selectedRun->status == RunStatus::Completed && selectedRun->outputModelPath.has_value()
    ) {
        postExportScreen_.Render(textureId, controller);
    } else {
        phaseScreen_.Render(*selectedRun, state.backendReady, state.logs, controller);
    }
}

void UIManager::EndFrame() {
    ImGui::Render();
    ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
}

void UIManager::Shutdown() {
    phaseScreen_.Shutdown();

    if (openGLBackendInitialized_) {
        ImGui_ImplOpenGL3_Shutdown();
        openGLBackendInitialized_ = false;
    }
    if (sdlBackendInitialized_) {
        ImGui_ImplSDL2_Shutdown();
        sdlBackendInitialized_ = false;
    }
    if (contextCreated_) {
        ImGui::DestroyContext();
        contextCreated_ = false;
    }
}

int UIManager::GetViewportWidth() const {
    return postExportScreen_.GetViewportWidth();
}

int UIManager::GetViewportHeight() const {
    return postExportScreen_.GetViewportHeight();
}

bool UIManager::IsViewportHovered() const {
    return postExportScreen_.IsViewportHovered();
}

bool UIManager::ConsumeRecenterRequest() {
    return postExportScreen_.ConsumeRecenterRequest();
}
