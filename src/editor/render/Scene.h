#pragma once

#include <memory>
#include <string>
#include <glad/gl.h>
#include <glm/glm.hpp>

#include "Camera.h"

class Model;
class Shader;

class Scene {
public:
	Scene();
	~Scene();

	void LoadModel(const std::string& objPath);
	void ClearModel();
	void Recenter();
	void Orbit(float deltaX, float deltaY);
	void Pan(float deltaX, float deltaY);
	void Zoom(float delta);
		
	void Update(float deltaTime);
	void Render(int viewportWidth, int viewportHeight);

	GLuint GetColorTexture();

	Camera& GetCamera();
	Model* GetModel();

private:
	void EnsureFramebuffer(int width, int height);
	void DestroyFramebuffer();

private:
	Camera camera_;
	std::unique_ptr<Model> model_;
	std::unique_ptr<Shader> shader_;

	glm::vec3 lightDir_{ -0.5f, -1.0f, -0.3f };
	glm::vec3 objectColor_{ 0.8f, 0.8f, 0.8f };
	GLuint colorTexture_ = 0;
	float ambientStrength_ = 0.8f;
	int colorMode_ = 0;

	GLuint depthRenderbuffer_ = 0;
	GLuint fbo_ = 0;
	int fboWidth_ = 0, fboHeight_ = 0;


};