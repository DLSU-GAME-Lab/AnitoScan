#include "editor/ui/UIManager.h"

#include <iostream>

#include <imgui.h>
#include <backends/imgui_impl_opengl3.h>
#include <backends/imgui_impl_sdl2.h>

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

void UIManager::Render(const EditorState& state, unsigned int textureId) {
    postExportScreen_.Render(state, textureId);
}

void UIManager::EndFrame() {
    ImGui::Render();
    ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
}

void UIManager::Shutdown() {
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
