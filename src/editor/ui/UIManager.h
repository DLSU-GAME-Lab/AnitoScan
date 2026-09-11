#pragma once

#include "editor/controller/ControllerTypes.h"
#include "editor/ui/UIInput.h"
#include "editor/ui/screens/PhaseScreen.h"
#include "editor/ui/screens/PostExportScreen.h"
#include "editor/ui/screens/RunSetupScreen.h"

#include <SDL.h>

#include <string>
#include <vector>

enum class UIScreen {
    RunSetup,
    Phase,
    PostExport
};

struct RunSetupData {
    std::vector<std::string> runNames;
    std::vector<std::string> runStatuses;
    std::vector<std::string> runIds;
    std::string message;
    std::string inputError;
    std::string rejectedInputSource;
    bool canCreateRun = false;
};


struct PostExportData {
    std::string runName;
    std::string statusText;
    PhaseNavigationData navigation;
    std::vector<std::string> outputModelPaths;
    std::string selectedOutputModelPath;
    unsigned int textureId = 0;
};

class UIManager {
public:
    ~UIManager();

    bool Initialize(SDL_Window* window, SDL_GLContext glContext);
    void Shutdown();
    void ProcessEvent(const SDL_Event& event);
    void BeginFrame();
    void EndFrame();

    void SwitchScreen(UIScreen screen);
    void SetRunSetupData(RunSetupData data);
    void SetPhaseData(PhaseDisplayData data);
    void SetPostExportData(PostExportData data);
    void Render();
    std::vector<UIInput> PollInputs();

    int GetViewportWidth() const;
    int GetViewportHeight() const;
    bool IsViewportHovered() const;
    bool ConsumeRecenterRequest();

private:
    UIScreen screen_ = UIScreen::RunSetup;
    RunSetupData runSetupData_;
    PhaseDisplayData phaseData_;
    PostExportData postExportData_;
    RunSetupScreen runSetupScreen_;
    PhaseScreen phaseScreen_;
    PostExportScreen postExportScreen_;
    std::vector<UIInput> inputs_;
    bool contextCreated_ = false;
    bool sdlBackendInitialized_ = false;
    bool openGLBackendInitialized_ = false;
};
