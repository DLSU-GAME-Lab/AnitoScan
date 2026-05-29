#include "App.h"
#include "UI/UIManager.h"

#define STB_IMAGE_IMPLEMENTATION
#include <stb_image.h>


App::App(int width, int height) {
	this->isRunning = false;
	this->window = nullptr;
	this->glContext = nullptr;
	this->screenWidth = width;
	this->screenHeight = height;
}

App::~App() {
	Cleanup();
}

void App::Initialize() {
	//SDL
	if (!InitializeSDL()) {
		std::cerr << "[ERROR]: SDL initialization failed: " << SDL_GetError() << std::endl;
		return;
	}

	//OPENGL
	if (!InitializeOpenGL()) {
		std::cerr << "[ERROR]: OpenGL initialization failed: " << SDL_GetError() << std::endl;
		return;
	}

	//IMGUI
	if (!UIManager::GetInstance()->Initialize(this->window, this->glContext, this->ipc)) {
		std::cerr << "[ERROR]: ImGui initialization failed: " << std::endl;
		return;
	}

	////IPC - dummy
	//if (!this->ipc.Start("src\\pipeline\\.venv\\Scripts\\python.exe", "src/pipeline/core/dummy.py")) {
	//	std::cerr << "[ERROR]: Failed to launch Python backend." << std::endl;
	//	return;
	//}

	//IPC - pipeline.py
	if (!this->ipc.Start("src\\pipeline\\.venv\\Scripts\\python.exe", "src/pipeline/core/pipeline.py --ipc")) {
		std::cerr << "[ERROR]: Failed to launch Python backend." << std::endl;
		return;
	}


	
	this->isRunning = true;
	std::cerr << "App is initialized and running." << std::endl;
}

bool App::InitializeSDL() {
	// initialize SDL
	if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) < 0) {
		std::cerr << "[ERROR]: SDL initialization failed: " << SDL_GetError() << std::endl;
		return false;
	}

	// set OpenGL Attributes
	SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
	SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
	SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
	SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
	SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24);

	float dpiScale = 1.25f;  
	int logicalW = static_cast<int>(this->screenWidth / dpiScale);   
	int logicalH = static_cast<int>(this->screenHeight / dpiScale);  

	// create the window
	//window = SDL_CreateWindow(
	//	"AnitoScan",
	//	SDL_WINDOWPOS_CENTERED,
	//	SDL_WINDOWPOS_CENTERED,
	//	this->screenWidth, this->screenHeight,
	//	SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN | SDL_WINDOW_RESIZABLE
	//);

	window = SDL_CreateWindow(
		"AnitoScan",
		SDL_WINDOWPOS_CENTERED,
		SDL_WINDOWPOS_CENTERED,
		logicalW, logicalH,
		SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN | SDL_WINDOW_RESIZABLE | SDL_WINDOW_MAXIMIZED
	);

	if (!window) {
		std::cerr << "[ERROR]: Creating window failed: " << SDL_GetError << std::endl;
		return false;
	}

	return true;
}

bool App::InitializeOpenGL() {
	// bind the OpenGL context to window
	this->glContext = SDL_GL_CreateContext(this->window);
	if (!glContext) {
		std::cerr << "[ERROR]: OpenGL Context creation failed: " << SDL_GetError() << std::endl;
	}

	SDL_GL_MakeCurrent(this->window, this->glContext);

	// enable v-sync
	SDL_GL_SetSwapInterval(1);

	return true;
}

// IPC and action decoder from the python backend
void App::PollBackend() {
	std::vector<BackendMessage> messages;
	this->ipc.Poll(messages);
	//UIPanel* ui = UIManager::GetInstance()->GetPanelByType(UIType::SCAN_PANEL);
	//ScanPanel* panel = static_cast<ScanPanel*>(ui);
	OverviewPanel* overview = (OverviewPanel*)UIManager::GetInstance()->GetPanelByType(UIType::OVERVIEW);
	LogPanel* log = (LogPanel*)UIManager::GetInstance()->GetPanelByType(UIType::LOG_PANEL);

	for (BackendMessage& msg : messages) {
		try {
			auto j = nlohmann::json::parse(msg.raw);

			if (msg.type == "log") {
				String text = j.value("text", "");
				log->PushLog(text);
				//panel->PushLog(text);
			}
			else if (msg.type == "workspace_ready") {
				String runName = j.value("run_name", "");
				std::cout << "[DEBUG] workspace_ready received, run_name: '" << runName << "'" << std::endl;
				if (!runName.empty()) {
					UIManager::GetInstance()->SetOutputToFileViewers(runName);
				}
			}
			else if (msg.type == "progress") {
				float value = j.value("value", 0.0f);
				String label = j.value("label", "");
			//	overview->SetProgress(value, label);
			}
			else if (msg.type == "done") {
				//overview->SetDone();
			}
			else if (msg.type == "error") {
				//panel->PushLog("[ERROR] " + j.value("text", "unknown error"));
				log->PushLog("[ERROR] " + j.value("text", "unknown error"));
			}
		}
		catch (const nlohmann::json::exception&){
			if (msg.raw.find("PROGRESS:") != std::string::npos) {
				try {
					int percent = std::stoi(msg.raw.substr(msg.raw.find(":") + 1));

					float overall = (percent / 100.0f) * 0.25f;
					String temp = "Phase 1: Capture " + std::to_string(percent);
				//	overview->SetProgress(overall, temp);
				}
				catch (...){}
			}
			else {
				//panel->PushLog("[RAW] " + msg.raw);
				log->PushLog("[RAW] " + msg.raw);
			}
 		}
	}
}

void App::Run()
{
	// main loop
	SDL_Event event;
	while (this->isRunning) {

		// handle window/input events
		while (SDL_PollEvent(&event)) {
			ImGui_ImplSDL2_ProcessEvent(&event);

			if (event.type == SDL_QUIT) {
				this->isRunning = false;
			}
		}

		this->PollBackend();

		// ImGui draw/render
		UIManager::GetInstance()->BeginNewFrame();
		UIManager::GetInstance()->DrawAllUIs();
		UIManager::GetInstance()->EndFrame();

		SDL_GL_SwapWindow(this->window);
	}
}


void App::Cleanup() {
	this->ipc.Shutdown();
	UIManager::GetInstance()->Shutdown();
	// destroy window frame
	if (this->glContext) {
		SDL_GL_DeleteContext(this->glContext);
	}

	if (this->window) {
		SDL_DestroyWindow(this->window);
	}

	SDL_Quit();
}
