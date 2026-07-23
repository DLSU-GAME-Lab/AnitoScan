#include "UIManager.h"

UIManager* UIManager::sharedInstance = nullptr;

// Creates and initializes ImGui context
bool UIManager::Initialize(SDL_Window* window, SDL_GLContext glContext, EditorState& state, PipelineController* controller, Scene& scene) {
    sharedInstance = new UIManager();

    IMGUI_CHECKVERSION();
    if (!ImGui::CreateContext()) {
        std::cerr << "[ERROR]: UIManager failed to create ImGui context." << std::endl;
        return false;
    }

    ImGuiIO& io = ImGui::GetIO(); (void)io;
    io.ConfigFlags |= ImGuiConfigFlags_DockingEnable | ImGuiConfigFlags_NavEnableKeyboard;
    ImGui::StyleColorsDark();

    if (!ImGui_ImplSDL2_InitForOpenGL(window, glContext)) {
        std::cerr << "[ERROR]: UIManager failed to initialize ImGui for SDL2." << std::endl;
        return false;
    }

    if (!ImGui_ImplOpenGL3_Init("#version 330")) {
        std::cerr << "[ERROR]: UIManager failed to initialize ImGui for OpenGL." << std::endl;
        return false;
    }

    // Pass the new state and controller to the panel creator
    sharedInstance->CreateUIPanels(state, controller, scene);

    return true;
}

void UIManager::CreateUIPanels(EditorState& state, PipelineController* controller, Scene& scene) {
    MenuToolbar* toolbar = new MenuToolbar("Menu Toolbar");
    Dockspace* dockSpace = new Dockspace("DockSpace");
    toolbar->SetDockspace(dockSpace);

    this->uiList.push_back(toolbar);
    this->uiMap[static_cast<UIPanel*>(toolbar)->GetName()] = toolbar;

    this->uiList.push_back(dockSpace);
    this->uiMap[static_cast<UIPanel*>(dockSpace)->GetName()] = dockSpace;

    UIPanel* overview = new OverviewPanel("Overview", state, controller);
    this->uiList.push_back(overview);
    this->uiMap[overview->GetName()] = overview;

    UIPanel* captureViewer = new FileViewer("Capture", Phase::CAPTURE, state);
    this->uiList.push_back(captureViewer);
    this->uiMap[captureViewer->GetName()] = captureViewer;

    UIPanel* maskingViewer = new FileViewer("Masking", Phase::MASKING, state);
    this->uiList.push_back(maskingViewer);
    this->uiMap[maskingViewer->GetName()] = maskingViewer;

    UIPanel* logPanel = new LogPanel("Log", state);
    this->uiList.push_back(logPanel);
    this->uiMap[logPanel->GetName()] = logPanel;

    UIPanel* maskingPopup = new MaskingPopup("Masking Popup", state, controller);
    this->uiList.push_back(maskingPopup);
    this->uiMap[maskingPopup->GetName()] = maskingPopup;

    UIPanel* viewport = new ViewportPanel("Viewport", scene, state);
    this->uiList.push_back(viewport);
    this->uiMap[viewport->GetName()] = viewport;

    UIPanel* input = new InputWindow("Input Window");
    this->uiList.push_back(input);
    this->uiMap[input->GetName()] = input;
}

UIManager* UIManager::GetInstance() {
	return sharedInstance;
}

UIManager::UIManager() {}

UIManager::~UIManager() {}

// Initiates frame loops
void UIManager::BeginNewFrame() {
	ImGui_ImplOpenGL3_NewFrame();
	ImGui_ImplSDL2_NewFrame();
	ImGui::NewFrame();
}

// Iterates through the layout list and fires Draw calls for every active panel layer
void UIManager::DrawAllUIs() {
	for (UIPanel* panel : this->uiList) {
		if (Contains(panel->GetType(), UIType::DOCKSPACE, UIType::MENU_TOOLBAR)) {
			if (!panel->IsActive()) panel->SetActive(true);
		}

		if(panel->IsActive())
			panel->Draw();
	}
}

// Dispatches instructions down to the OpenGL renderer
void UIManager::EndFrame() {
	ImGui::Render();
	ImGuiIO& io = ImGui::GetIO();
	glViewport(0, 0, (int)io.DisplaySize.x, (int)io.DisplaySize.y);
	glClear(GL_COLOR_BUFFER_BIT);
	ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
}

// Returns registered UIPanel according to its name from the map attribute
UIPanel* UIManager::GetPanelByName(String name) {
	return this->uiMap[name];
}

// Returns registered UIPanel according to its type
UIPanel* UIManager::GetPanelByType(UIType type) {
	UIPanel* ret = nullptr;
	for (UIPanel* panel : this->uiList) {
		if (panel->GetType() == type) {
			ret = panel;
			break;
		}
	}
	return ret;
}

// Searches for the UIPanel by its type and activates it
void UIManager::OpenPanel(UIType type) {
	GetPanelByType(type)->SetActive(true);
}

void UIManager::ClosePanel(UIType type) {
	GetPanelByType(type)->SetActive(false);
}

// Clean up
void UIManager::Shutdown() {
	ImGui_ImplOpenGL3_Shutdown();
	ImGui_ImplSDL2_Shutdown();
	ImGui::DestroyContext();

	for (UIPanel* panel : this->uiList)
		delete panel;

	uiList.clear();
	uiMap.clear();
}

// Sets the authoritative backend workspace on all file viewer instances.
void UIManager::SetWorkspaceForFileViewers(const std::filesystem::path& workspace) {
	for (UIPanel* panel : this->uiList) {
		if (panel->GetType() == UIType::FILE_VIEWER_CAPTURE || panel->GetType() == UIType::FILE_VIEWER_MASKING) {
			FileViewer* temp = static_cast<FileViewer*>(panel);
			temp->SetWorkspaceToView(workspace);
		}
	}
}

void UIManager::ClearWorkspaceFromFileViewers() {
	for (UIPanel* panel : this->uiList) {
		if (panel->GetType() == UIType::FILE_VIEWER_CAPTURE || panel->GetType() == UIType::FILE_VIEWER_MASKING) {
			FileViewer* temp = static_cast<FileViewer*>(panel);
			temp->ClearWorkspace();
		}
	}
}

void UIManager::ApplyLayout(UILayout layout) {
	Dockspace* dockspace = static_cast<Dockspace*>(GetPanelByType(UIType::DOCKSPACE));

	switch (layout) {
	case UILayout::DEFAULT:{
		for (UIPanel* panel : this->uiList) {
		    if (Contains(panel->GetType(), UIType::FILE_VIEWER_CAPTURE, UIType::FILE_VIEWER_MASKING, UIType::LOG_PANEL, UIType::OVERVIEW, UIType::VIEWPORT, UIType::MASKING_MODAL)) {
                panel->SetActive(true);
            } else {
                panel->SetActive(false);
            }
		}
		dockspace->RequestDefaultLayout();
;		break;
		}
	case UILayout::MODEL_VIEWER: {
		for (UIPanel* panel : this->uiList) {
			if (Contains(panel->GetType(), UIType::VIEWPORT)) {
				panel->SetActive(true);
			}
			else {
				panel->SetActive(false);
			}
		}
		dockspace->RequestModelViewerLayout();
		break;
	}
	}

}

//void UIManager::ApplyLayout(UILayout layout) {
//	switch (layout) {
//	case UILayout::DEFAULT: {
//
//
//
//		/*this->uiMap["Overview"]->
//		this->uiMap["Logl"]->SetActive(true);
//		this->uiMap["Masking"]->SetActive(true);
//		this->uiMap["Capture"]->SetActive(true);*/
//		break;
//		}
//	}
//}
