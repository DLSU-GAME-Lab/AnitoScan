#include "App.h"
#include "UI/UIManager.h"

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

	this->scene = std::make_unique<Scene>();
	//IMGUI
	if (!UIManager::GetInstance()->Initialize(this->window, this->glContext, this->ipc, *this->scene)) {
		std::cerr << "[ERROR]: ImGui initialization failed: " << std::endl;
		return;
	}
	
	//IPC - pipeline.py
	//if (!this->ipc.Start("src\\pipeline\\.venv\\Scripts\\python.exe", "src/pipeline/core/pipeline.py --ipc")) {
	//	std::cerr << "[ERROR]: Failed to launch Python backend." << std::endl;
	//	return;
	//}

	// 1. Get the true project root folder from your CMake macro
	std::filesystem::path projectRoot(PROJECT_ROOT_DIR);

	// 2. Target 'uv' as the primary executable instead of the internal .venv python
	// Note: This assumes 'uv' is installed globally in the system path. 
	// On Windows, you can just pass "uv" or "uv.exe" as the application name.
	std::string uvExecutable = "uv";

	// 3. Build the explicit absolute path to the core script in your source tree
	std::filesystem::path pythonScript = projectRoot / "src" / "pipeline" / "core" / "pipeline.py";

	// 4. Prepare arguments: Tell UV to 'run python' followed by your script and flags
	std::string commandArgs = "run python \"" + pythonScript.string() + "\" --ipc";

	std::cout << "[DEBUG] Spawning process manager: " << uvExecutable << std::endl;
	std::cout << "[DEBUG] UV Run Arguments: " << commandArgs << std::endl;

	// 5. Start the process via UV
	if (!this->ipc.Start(uvExecutable.c_str(), commandArgs.c_str())) {
		std::cerr << "[ERROR]: Failed to launch UV package manager backend." << std::endl;
	}
	
	this->lastTime = SDL_GetPerformanceCounter();
	this->isRunning = true;
	std::cout << "[DEBUG]: App is initialized and running." << std::endl;
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

	if (!gladLoadGL((GLADloadfunc)SDL_GL_GetProcAddress)) {
		std::cerr << "[ERROR]: Failed to initialize glad." << std::endl;
		return false;
	}

	return true;
}

// IPC and action decoder from the python backend
void App::PollBackend() {
	std::vector<BackendMessage> messages;
	this->ipc.Poll(messages);

	if (messages.empty()) return;

	OverviewPanel* overview = static_cast<OverviewPanel*>(UIManager::GetInstance()->GetPanelByType(UIType::OVERVIEW));
	LogPanel* log = static_cast<LogPanel*>(UIManager::GetInstance()->GetPanelByType(UIType::LOG_PANEL));
	MaskingPopup* popup = static_cast<MaskingPopup*>(UIManager::GetInstance()->GetPanelByType(UIType::MASKING_MODAL));
	ViewportPanel* viewport = static_cast<ViewportPanel*>(UIManager::GetInstance()->GetPanelByType(UIType::VIEWPORT));

	for (BackendMessage& msg : messages) {
		try {
			auto j = nlohmann::json::parse(msg.raw);

			// LOG
			if (msg.type == "log") {
				String text = j.value("text", "");
				log->PushLog(text);
			}

			// INITIALIZED WORKSPACE
			else if (msg.type == "workspace_ready") {
				String runName = j.value("run_name", "");
				std::cout << "[DEBUG]: workspace_ready received, run_name: '" << runName << "'" << std::endl;
				if (!runName.empty()) {
					UIManager::GetInstance()->SetOutputToFileViewers(runName);
				}
			}

			// PROGRESS UPDATE
			else if (msg.type == "progress") {
				float value = j.value("value", 0.0f);
				String label = j.value("label", "");
				int phase = j.value("phase", 0);
				
				//route to the correct phase bar
				if (phase >= 1 && phase <= (int)Phase::COUNT) {
					overview->SetPhaseProgress((Phase)(phase - 1), value, label);
					if (value == 1.f) {
						overview->SetPhaseComplete((Phase)(phase - 1));
						std::cout << "[DEBUG]: " << label << std::endl;
					}
				}
				else {		//overall progress bar
					overview->SetPhaseProgress(overview->GetCurrentPhase(), value, label);
				}
			}

			// MASKING POPUP
			else if (msg.type == "action_required") { //pass the image index
				String previewPath = j.value("preview", "");
				String frame = j.value("frame", "");
				int count = j.value("count", 0);
				std::cout << "[DEBUG] action_required: " << previewPath << std::endl;

				popup->ShowCandidates(previewPath, frame, count);
			}
			
			// SCAN COMPLETE
			else if (msg.type == "done") {
				overview->SetDone();
				String baseDir = j["data"].value("output", "");
				String outputName = j["data"].value("run_name", "");
				
				viewport->LoadOutputModel(outputName, overview->GetExportQuality());

				std::cout << "[DEBUG]: Scan Complete" << std::endl;
				std::cout << "[DEBUG]: Output in: " << baseDir << std::endl;
			}

			// ERROR
			else if (msg.type == "error") {
				log->PushLog("[ERROR] " + j.value("text", "unknown error"));
			}
		}

		// RAW prints from backend
		catch (const nlohmann::json::exception&){
			//std::cout << "[RAW]: " + msg.raw << std::endl;
			log->PushLog(msg.raw);
 		}
	}
}

void App::ProcessMouseEvents(SDL_Event event) {
	ViewportPanel* viewport = static_cast<ViewportPanel*>(UIManager::GetInstance()->GetPanelByType(UIType::VIEWPORT));
	bool canStartOrbit = viewport && viewport->IsHovered();

	//MOUSE DOWN
	if (event.type == SDL_MOUSEBUTTONDOWN && canStartOrbit) {
		if (event.button.button == SDL_BUTTON_LEFT) {
			this->mouseDragging = true;
		}
		else if (event.button.button == SDL_BUTTON_MIDDLE) {
			this->middleMousehold = true;
		}
		SDL_SetRelativeMouseMode(SDL_TRUE);
	}

	//RELEASE
	else if (event.type == SDL_MOUSEBUTTONUP) {
		if (event.button.button == SDL_BUTTON_LEFT) {
			this->mouseDragging = false;
		}
		else if (event.button.button == SDL_BUTTON_MIDDLE) {
			this->middleMousehold = false;
		}
		SDL_SetRelativeMouseMode(SDL_FALSE);
	}

	// adjust camera rotation when dragging mouse
	else if (event.type == SDL_MOUSEMOTION && this->mouseDragging) {
		this->scene->GetCamera().ProcessMouseDrag(
			static_cast<float>(event.motion.xrel),
			static_cast<float>(event.motion.yrel)
		);
	}

	// pan camera when dragging middle mouse button
	else if (event.type == SDL_MOUSEMOTION && this->middleMousehold) {
		this->scene->GetCamera().ProcessPan(
			static_cast<float>(event.motion.xrel),
			static_cast<float>(event.motion.yrel)
		);
	}

	// mouse wheel function
	else if (event.type == SDL_MOUSEWHEEL && (canStartOrbit || this->mouseDragging)) {
		this->scene->GetCamera().ProcessScroll(static_cast<float>(event.wheel.y));
	}


	//safety net when mouse input exits window 
	if (event.type == SDL_WINDOWEVENT &&
		(event.window.event == SDL_WINDOWEVENT_FOCUS_LOST ||
			event.window.event == SDL_WINDOWEVENT_LEAVE)) {
		mouseDragging = false;
		SDL_SetRelativeMouseMode(SDL_FALSE);
	}
}

void App::ProcessKeyboardEvents(SDL_Event event) {
	if (event.type == SDL_KEYDOWN && event.key.keysym.sym == SDLK_f) {
		this->scene->Recenter();
	}
}


void App::Run()
{
	// main loop
	SDL_Event event;
	while (this->isRunning) {
		//deltaTime
		Uint64 now = SDL_GetPerformanceCounter();
		this->deltaTime = static_cast<float>(now - this->lastTime) / SDL_GetPerformanceFrequency();
		this->lastTime = now;
		this->deltaTime = (std::min)(deltaTime, 0.05f);

		// handle window/input events
		while (SDL_PollEvent(&event)) {
			ImGui_ImplSDL2_ProcessEvent(&event);
			if (event.type == SDL_QUIT) {
				this->isRunning = false;
			}

			ProcessMouseEvents(event);
			ProcessKeyboardEvents(event);	
		}


		const Uint8* keys = SDL_GetKeyboardState(nullptr);
		scene->GetCamera().ProcessKeyboard(
			keys[SDL_SCANCODE_LEFT],
			keys[SDL_SCANCODE_RIGHT],
			keys[SDL_SCANCODE_UP],
			keys[SDL_SCANCODE_DOWN],
			deltaTime
		);


		// Receiver and action decoder from python backend
		PollBackend();

		// model render
		int drawableW, drawableH;
		SDL_GL_GetDrawableSize(this->window, &drawableW, &drawableH);
		scene->Update(0.0f);
		scene->Render(drawableW, drawableH);

		//ImGui draw/render
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
