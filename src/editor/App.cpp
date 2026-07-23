#include "App.h"
#include "UI/UIManager.h"
#include "IPCProtocol.h"

#include <utility>

App::App(int width, int height, BackendLaunchConfig backendConfig)
	: backendConfig(std::move(backendConfig)) {
	this->isRunning = false;
	this->window = nullptr;
	this->glContext = nullptr;
	this->screenWidth = width;
	this->screenHeight = height;
}

App::~App() {
	Cleanup();
}

bool App::Initialize() {
	if (!InitializeSDL()) {
		std::cerr << "[ERROR]: SDL initialization failed: " << SDL_GetError() << std::endl;
		return false;
	}

	if (!InitializeOpenGL()) {
		std::cerr << "[ERROR]: OpenGL initialization failed: " << SDL_GetError() << std::endl;
		return false;
	}

	this->scene = std::make_unique<Scene>();
	if (!UIManager::GetInstance()->Initialize(this->window, this->glContext, this->ipc, *this->scene)) {
		std::cerr << "[ERROR]: ImGui initialization failed: " << std::endl;
		return false;
	}

	std::cout << "[DEBUG]: Launching " << this->backendConfig.displayName << " backend." << std::endl;
	if (!this->ipc.Start(this->backendConfig.executable, this->backendConfig.arguments)) {
		std::cerr << "[ERROR]: Failed to launch " << this->backendConfig.displayName << " backend." << std::endl;
		return false;
	}

	this->lastTime = SDL_GetPerformanceCounter();
	this->isRunning = true;
	std::cout << "[DEBUG]: App is initialized and running." << std::endl;
	return true;
}

bool App::InitializeSDL() {
	if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) < 0) {
		std::cerr << "[ERROR]: SDL initialization failed: " << SDL_GetError() << std::endl;
		return false;
	}

	SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
#if defined(__APPLE__)
	SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 4);
	SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 1);
	SDL_GL_SetAttribute(SDL_GL_CONTEXT_FLAGS, SDL_GL_CONTEXT_FORWARD_COMPATIBLE_FLAG);
#else
	SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
	SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
#endif
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
		SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN | SDL_WINDOW_RESIZABLE |
		SDL_WINDOW_MAXIMIZED | SDL_WINDOW_ALLOW_HIGHDPI
	);

	if (!window) {
		std::cerr << "[ERROR]: Creating window failed: " << SDL_GetError() << std::endl;
		return false;
	}

	return true;
}

bool App::InitializeOpenGL() {
	this->glContext = SDL_GL_CreateContext(this->window);
	if (!glContext) {
		std::cerr << "[ERROR]: OpenGL Context creation failed: " << SDL_GetError() << std::endl;
		return false;
	}

	if (SDL_GL_MakeCurrent(this->window, this->glContext) != 0) {
		std::cerr << "[ERROR]: Failed to activate OpenGL context: " << SDL_GetError() << std::endl;
		return false;
	}

	SDL_GL_SetSwapInterval(1);

	if (!gladLoadGL((GLADloadfunc)SDL_GL_GetProcAddress)) {
		std::cerr << "[ERROR]: Failed to initialize glad." << std::endl;
		return false;
	}

	return true;
}

void App::PollBackend() {
	std::vector<BackendMessage> messages;
	this->ipc.Poll(messages);

	if (messages.empty()) return;

	OverviewPanel* overview = static_cast<OverviewPanel*>(UIManager::GetInstance()->GetPanelByType(UIType::OVERVIEW));
	LogPanel* log = static_cast<LogPanel*>(UIManager::GetInstance()->GetPanelByType(UIType::LOG_PANEL));
	MaskingPopup* popup = static_cast<MaskingPopup*>(UIManager::GetInstance()->GetPanelByType(UIType::MASKING_MODAL));
	ViewportPanel* viewport = static_cast<ViewportPanel*>(UIManager::GetInstance()->GetPanelByType(UIType::VIEWPORT));

	for (BackendMessage& msg : messages) {
		IPCProtocol::DecodedEvent event = IPCProtocol::DecodeEvent(msg.raw);

		switch (event.type) {
			case IPCProtocol::EventType::BACKEND_READY:
				if (event.backendReady.protocolVersion != IPCProtocol::PROTOCOL_VERSION) {
					std::cerr << "[ERROR]: Protocol version mismatch. Backend reported version "
					          << event.backendReady.protocolVersion << ", expected "
					          << IPCProtocol::PROTOCOL_VERSION << ". Shutting down." << std::endl;
					if (log) log->PushLog("[ERROR] Backend protocol version mismatch!");
					this->ipc.Shutdown();
					this->isRunning = false;
					return;
				} else {
					std::cout << "[DEBUG]: Backend ready, protocol_version: " << event.backendReady.protocolVersion << std::endl;
				}
				break;

			case IPCProtocol::EventType::LOG:
				if (log) log->PushLog(event.log.text);
				break;

			case IPCProtocol::EventType::WORKSPACE_READY:
				UIManager::GetInstance()->SetWorkspaceForFileViewers(event.workspaceReady.workspace);
				break;

			case IPCProtocol::EventType::PHASE_STARTED:
				if (overview) overview->SetPhaseStarted(event.phaseStarted.phase, event.phaseStarted.label);
				break;

			case IPCProtocol::EventType::PROGRESS:
				if (overview) {
					overview->SetPhaseProgress(
						event.progress.phase,
						event.progress.value,
						event.progress.overallValue,
						event.progress.label
					);
				}
				break;

			case IPCProtocol::EventType::ACTION_REQUIRED:
				if (popup) {
					popup->ShowCandidates(
						event.actionRequired.requestId,
						event.actionRequired.preview,
						event.actionRequired.frame,
						event.actionRequired.count
					);
				}
				break;

			case IPCProtocol::EventType::PHASE_COMPLETED:
				if (overview) overview->SetPhaseComplete(event.phaseCompleted.phase);
				break;

			case IPCProtocol::EventType::DONE:
				if (overview) overview->SetDone();
				if (viewport && !event.done.output.empty()) {
					viewport->LoadOutputModel(event.done.output);
				}
				break;

			case IPCProtocol::EventType::CANCELLED:
				if (overview) overview->SetCancelled();
				break;

			case IPCProtocol::EventType::ERROR:
				if (log) log->PushLog("[ERROR] " + event.error.text);
				if (overview) overview->HandleError(event.error);
				break;

			default:
				if (log) log->PushLog(msg.raw);
				break;
		}
	}
}

void App::ProcessMouseEvents(SDL_Event event) {
	ViewportPanel* viewport = static_cast<ViewportPanel*>(UIManager::GetInstance()->GetPanelByType(UIType::VIEWPORT));
	bool canStartOrbit = viewport && viewport->IsHovered();

	if (event.type == SDL_MOUSEBUTTONDOWN && canStartOrbit) {
		if (event.button.button == SDL_BUTTON_LEFT) {
			this->mouseDragging = true;
		}
		else if (event.button.button == SDL_BUTTON_MIDDLE) {
			this->middleMousehold = true;
		}
		SDL_SetRelativeMouseMode(SDL_TRUE);
	}
	else if (event.type == SDL_MOUSEBUTTONUP) {
		if (event.button.button == SDL_BUTTON_LEFT) {
			this->mouseDragging = false;
		}
		else if (event.button.button == SDL_BUTTON_MIDDLE) {
			this->middleMousehold = false;
		}
		SDL_SetRelativeMouseMode(SDL_FALSE);
	}
	else if (event.type == SDL_MOUSEMOTION && this->mouseDragging) {
		this->scene->GetCamera().ProcessMouseDrag(
			static_cast<float>(event.motion.xrel),
			static_cast<float>(event.motion.yrel)
		);
	}
	else if (event.type == SDL_MOUSEMOTION && this->middleMousehold) {
		this->scene->GetCamera().ProcessPan(
			static_cast<float>(event.motion.xrel),
			static_cast<float>(event.motion.yrel)
		);
	}
	else if (event.type == SDL_MOUSEWHEEL && (canStartOrbit || this->mouseDragging)) {
		this->scene->GetCamera().ProcessScroll(static_cast<float>(event.wheel.y));
	}

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

void App::Run() {
	SDL_Event event;
	while (this->isRunning) {
		Uint64 now = SDL_GetPerformanceCounter();
		this->deltaTime = static_cast<float>(now - this->lastTime) / SDL_GetPerformanceFrequency();
		this->lastTime = now;
		this->deltaTime = (std::min)(deltaTime, 0.05f);

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

		PollBackend();

		int drawableW, drawableH;
		SDL_GL_GetDrawableSize(this->window, &drawableW, &drawableH);
		scene->Update(0.0f);
		scene->Render(drawableW, drawableH);

		UIManager::GetInstance()->BeginNewFrame();
		UIManager::GetInstance()->DrawAllUIs();
		UIManager::GetInstance()->EndFrame();

		SDL_GL_SwapWindow(this->window);
	}
}

void App::Cleanup() {
	this->ipc.Shutdown();
	UIManager::GetInstance()->Shutdown();
	if (this->glContext) {
		SDL_GL_DeleteContext(this->glContext);
	}
	if (this->window) {
		SDL_DestroyWindow(this->window);
	}
	SDL_Quit();
}
