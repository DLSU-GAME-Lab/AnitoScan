#pragma once

#include <iostream>

#include <glad/gl.h>
#include <SDL.h>
#include <SDL_opengl.h>
#include <backends/imgui_impl_sdl2.h>
#include <backends/imgui_impl_opengl3.h>

#include "IPCClient.h"
#include "Types.h"
#include "render/Scene.h"

class IPCClient;

class App {
public:
	App(int width, int height);
	~App();

	void Initialize();
	void Run();

private:
	bool InitializeSDL();
	bool InitializeOpenGL();
	void PollBackend();
	void Cleanup();

private:
	bool isRunning;
	SDL_Window* window;
	SDL_GLContext glContext;

	int screenWidth;
	int screenHeight;

	IPCClient ipc;
	std::unique_ptr<Scene> scene;
	bool mouseDragging = false;

};