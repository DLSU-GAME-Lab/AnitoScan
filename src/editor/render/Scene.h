#pragma once

#include <memory>
#include <string>
#include "Camera.h"
#include "Model.h"
#include "Shader.h"

class Scene {
public:
	Scene();
	~Scene();

	void LoadModel(const String& objPath);
	void Recenter();
	
	void Update(float deltaTime);
	void Render(int viewportWidth, int viewportHeight);

	GLuint GetColorTexture();

	Camera& GetCamera();
	Model* GetModel();

private:
	void EnsureFramebuffer(int width, int height);
	void DestroyFramebuffer();

private:
	Camera camera;
	std::unique_ptr<Model> model;
	std::unique_ptr<Shader> shader;

	glm::vec3 lightDir{ -0.5f, -1.0f, -0.3f };
	glm::vec3 objectColor{ 0.8f, 0.8f, 0.8f };
	GLuint colorTexture = 0;
	float ambientStrength = 0.8f;
	int colorMode = 0;

	GLuint depthRenderbuffer = 0;
	GLuint fbo = 0;
	int fboWidth = 0, fboHeight = 0;


};