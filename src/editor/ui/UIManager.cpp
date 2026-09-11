#include "editor/ui/UIManager.h"

#include "editor/ui/UIStyle.h"

#include <iostream>
#include <utility>

#include <backends/imgui_impl_opengl3.h>
#include <backends/imgui_impl_sdl2.h>
#include <imgui.h>

UIManager::~UIManager() {
    Shutdown();
}

bool UIManager::Initialize(SDL_Window* window, SDL_GLContext glContext) {
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    contextCreated_ = true;
    UIStyle::ApplyTheme();

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

void UIManager::ProcessEvent(const SDL_Event& event) {
    ImGui_ImplSDL2_ProcessEvent(&event);
}

void UIManager::BeginFrame() {
    ImGui_ImplOpenGL3_NewFrame();
    ImGui_ImplSDL2_NewFrame();
    ImGui::NewFrame();
}

void UIManager::EndFrame() {
    ImGui::Render();
    ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
}

void UIManager::SwitchScreen(UIScreen screen) {
    if (screen_ == UIScreen::Phase && screen != UIScreen::Phase) {
        phaseScreen_.ResetInteraction();
    }
    screen_ = screen;
}

void UIManager::SetRunSetupData(RunSetupData data) {
    runSetupData_ = std::move(data);
}

void UIManager::SetPhaseData(PhaseDisplayData data) {
    if (data.kind != PhaseDisplayKind::MaskSelection || !data.maskSelectionEnabled ||
        data.selectionSubmitting || data.runId != phaseData_.runId ||
        data.selectionId != phaseData_.selectionId) {
        phaseScreen_.ResetInteraction();
    }
    phaseData_ = std::move(data);
}

void UIManager::SetPostExportData(PostExportData data) {
    postExportData_ = std::move(data);
}

void UIManager::Render() {
    switch (screen_) {
    case UIScreen::RunSetup:
        runSetupScreen_.Render(runSetupData_, inputs_);
        break;
    case UIScreen::Phase:
        phaseScreen_.Render(phaseData_, inputs_);
        break;
    case UIScreen::PostExport:
        postExportScreen_.Render(postExportData_, inputs_);
        break;
    }
}

std::vector<UIInput> UIManager::PollInputs() {
    std::vector<UIInput> inputs = std::move(inputs_);
    inputs_.clear();
    return inputs;
}

int UIManager::GetViewportWidth() const {
    return screen_ == UIScreen::PostExport ? postExportScreen_.GetViewportWidth() : 0;
}

int UIManager::GetViewportHeight() const {
    return screen_ == UIScreen::PostExport ? postExportScreen_.GetViewportHeight() : 0;
}

bool UIManager::IsViewportHovered() const {
    return screen_ == UIScreen::PostExport && postExportScreen_.IsViewportHovered();
}

bool UIManager::ConsumeRecenterRequest() {
    return postExportScreen_.ConsumeRecenterRequest();
}
