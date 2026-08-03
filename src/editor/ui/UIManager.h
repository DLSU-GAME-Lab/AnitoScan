#pragma once

#include <SDL.h>

#include "editor/ui/screens/PostExportScreen.h"

struct EditorState;

class UIManager {
public:
    ~UIManager();

    bool Initialize(SDL_Window* window, SDL_GLContext glContext);
    void ProcessEvent(const SDL_Event& event);
    void BeginFrame();
    void Render(const EditorState& state, unsigned int textureId);
    void EndFrame();
    void Shutdown();

    int GetViewportWidth() const;
    int GetViewportHeight() const;

private:
    PostExportScreen postExportScreen_;
    bool contextCreated_ = false;
    bool sdlBackendInitialized_ = false;
    bool openGLBackendInitialized_ = false;
};
