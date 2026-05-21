#include "UIManager.h"

UIManager* UIManager::sharedInstance = nullptr;

bool UIManager::Initialize(SDL_Window* window, SDL_GLContext glContext, IPCClient& ipc) {
	sharedInstance = new UIManager();

	// create ImGui context and IO
	IMGUI_CHECKVERSION();

	if (!ImGui::CreateContext()) {
		std::cerr << "[ERROR]: UIManager failed to create ImGui context." << std::endl;
		return false;
	}

	ImGuiIO& io = ImGui::GetIO(); (void)io;
	io.ConfigFlags |= ImGuiConfigFlags_DockingEnable, ImGuiConfigFlags_NavEnableKeyboard;
	ImGui::StyleColorsDark();

	if (!ImGui_ImplSDL2_InitForOpenGL(window, glContext)) {
		std::cerr << "[ERROR]: UIManager failed to initialize ImGui for SDL2." << std::endl;
		return false;
	}

	if (!ImGui_ImplOpenGL3_Init("#version 330")) {
		std::cerr << "[ERROR]: UIManager failed to initialize ImGui for OpenGL." << std::endl;
		return false;
	}

	sharedInstance->CreateUIPanels(ipc);

	return true;
}

// Create and register the UI Panels
void UIManager::CreateUIPanels(IPCClient& ipc) {
	ScanPanel* scanPanel = new ScanPanel(ipc);
	this->uiList.push_back(scanPanel);
	this->uiMap[UIType::SCAN_PANEL] = scanPanel;
	
	DockSpace* dockSpace = new DockSpace();
	this->uiList.push_back(dockSpace);
	this->uiMap[UIType::DOCKSPACE] = dockSpace;
}

UIManager* UIManager::GetInstance() {
	return sharedInstance;
}

UIManager::UIManager() {}
	
UIManager::~UIManager() {}

// new frame
void UIManager::BeginNewFrame() {
	ImGui_ImplOpenGL3_NewFrame();
	ImGui_ImplSDL2_NewFrame();
	ImGui::NewFrame();
}

// draw
void UIManager::DrawAllUIs() {
	for (UIPanel* panel : this->uiList) {
		if(panel->IsActive())
			panel->Draw();
	}
}

// render
void UIManager::EndFrame() {
	ImGui::Render();
	ImGuiIO& io = ImGui::GetIO();
	glViewport(0, 0, (int)io.DisplaySize.x, (int)io.DisplaySize.y);
	glClear(GL_COLOR_BUFFER_BIT);
	ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
}

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

void UIManager::Shutdown() {
	ImGui_ImplOpenGL3_Shutdown();
	ImGui_ImplSDL2_Shutdown();
	ImGui::DestroyContext();

	for (UIPanel* panel : this->uiList)
		delete panel;

	uiList.clear();
	uiMap.clear();
}
