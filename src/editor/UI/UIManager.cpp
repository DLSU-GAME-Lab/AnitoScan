#include "UIManager.h"

UIManager* UIManager::sharedInstance = nullptr;

// Creates and initializes ImGui context
bool UIManager::Initialize(SDL_Window* window, SDL_GLContext glContext, IPCClient& ipc, Scene& scene) {
	sharedInstance = new UIManager();

	// create ImGui context and IO
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

	sharedInstance->CreateUIPanels(ipc, scene);

	return true;
}

// Create and register the UI Panels
void UIManager::CreateUIPanels(IPCClient& ipc, Scene& scene) {
	DockSpace* dockSpace = new DockSpace("DockSpace");
	this->uiList.push_back(dockSpace);
	this->uiMap[dockSpace->GetName()] = dockSpace;

	OverviewPanel* overview = new OverviewPanel("Overview", ipc);
	this->uiList.push_back(overview);
	this->uiMap[overview->GetName()] = overview;

	FileViewer* captureViewer = new FileViewer("Capture", Phase::CAPTURE);
	this->uiList.push_back(captureViewer);
	this->uiMap[captureViewer->GetName()] = captureViewer;

	FileViewer* maskingViewer = new FileViewer("Masking", Phase::MASKING);
	this->uiList.push_back(maskingViewer);
	this->uiMap[maskingViewer->GetName()] = maskingViewer;

	//FileViewer* spatialViewer = new FileViewer("Spatial", Phase::SPATIAL);
	//this->uiList.push_back(spatialViewer);
	//this->uiMap[spatialViewer->GetName()] = spatialViewer;

	LogPanel* logPanel = new LogPanel("Log", ipc);
	this->uiList.push_back(logPanel);
	this->uiMap[logPanel->GetName()] = logPanel;

	MaskingPopup* maskingPopup = new MaskingPopup("Masking Popup", ipc);
	this->uiList.push_back(maskingPopup);
	this->uiMap[maskingPopup->GetName()] = maskingPopup;

	ViewportPanel* viewport = new ViewportPanel("Model Viewer", scene);
	this->uiList.push_back(viewport);
	this->uiMap[viewport->GetName()] = viewport;

	InputWindow* input = new InputWindow("Input Window");
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
void UIManager::OpenUI(UIType type) {
	GetPanelByType(type)->SetActive(true);
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

// Sets the output folder to all file viewer instances (capture, masking, etc)
void UIManager::SetOutputToFileViewers(std::filesystem::path output) {
	for (UIPanel* panel : this->uiList) {
		if (panel->GetType() == UIType::FILE_VIEWER) {
			FileViewer* temp = static_cast<FileViewer*>(panel);
			temp->SetOutputFolderToView(output);
		}
	}
}
