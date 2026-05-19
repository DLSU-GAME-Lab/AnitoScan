#pragma once

#include <iostream>

#include <SDL.h>
#include <SDL_opengl.h>
#include <backends/imgui_impl_sdl2.h>
#include <backends/imgui_impl_opengl3.h>

class App {
public:
	App(int width, int height);
	~App();

	void Initialize();
	void Run();

private:
	bool InitializeSDL();
	bool InitializeOpenGL();
	void Cleanup();

	bool isRunning;
	SDL_Window* window;
	SDL_GLContext glContext;

	int screenWidth;
	int screenHeight;

};