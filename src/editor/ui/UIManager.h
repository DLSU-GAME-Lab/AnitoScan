#pragma once

#include <SDL.h>

#include "editor/ui/screens/PhaseScreen.h"
#include "editor/ui/screens/PostExportScreen.h"
#include "editor/ui/screens/RunSetupScreen.h"

struct EditorState;
class PipelineController;

class UIManager {
public:
    ~UIManager();

    bool Initialize(SDL_Window* window, SDL_GLContext glContext);
    void ProcessEvent(const SDL_Event& event);
    void BeginFrame();
    void Render(const EditorState& state, PipelineController& controller, unsigned int textureId);
    void EndFrame();
    void Shutdown();

    int GetViewportWidth() const;
    int GetViewportHeight() const;

private:
    RunSetupScreen runSetupScreen_;
    PhaseScreen phaseScreen_;
    PostExportScreen postExportScreen_;
    bool contextCreated_ = false;
    bool sdlBackendInitialized_ = false;
    bool openGLBackendInitialized_ = false;
};
