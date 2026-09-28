#include "Scene.h"

#include "Model.h"
#include "Shader.h"

#include <cmath>
#include <iostream>
#include <memory>

// Initializes the scene with a default camera position  and creates the default shader used for rendering.
Scene::Scene() : camera_(glm::vec3(0.0f, 0.0f, 3.0f), 5.0f) {
	shader_ = std::make_unique<Shader>("shaders/default.vert", "shaders/default.frag");
	//shader = std::make_unique<Shader>("default.vert", "default.frag");
}

Scene::~Scene() {
	DestroyFramebuffer();
}

// Loads a 3D model from file and adjustments on camera
void Scene::LoadModel(const std::string& objPath) {
	model_ = std::make_unique<Model>(objPath);
	Recenter();
}

void Scene::ClearModel() {
	model_.reset();
}

void Scene::Orbit(float deltaX, float deltaY) {
	camera_.ProcessMouseDrag(deltaX, deltaY);
}

void Scene::Pan(float deltaX, float deltaY) {
	camera_.ProcessPan(deltaX, deltaY);
}

void Scene::Zoom(float delta) {
	camera_.ProcessScroll(delta);
}

// Recalculates camera distance and target orientation based on the active model's bounds.
void Scene::Recenter() {
	if (!model_) return;

	glm::vec3 center = model_->GetCentroid();
	float radius = model_->GetBoundsRadius();

	float fovRadians = glm::radians(45.0f);
	float distance = (radius / std::sin(fovRadians * 0.5f)) * 1.5f;
	
	camera_.SetTarget(center);
	camera_.SetDistance(distance);

	std::cout << "[Scene] Recentered camera: target(" << center.x << ", " << center.y << ", " << center.z
		<< ") distance(" << distance << ")\n";
}

// Updates scene transformations, step logics, and animations over time
void Scene::Update(float deltaTime) {}


// Deletes OpenGL color textures, depth renderbuffers, and framebuffers to clear memory
void Scene::DestroyFramebuffer() {
	if (colorTexture_) glDeleteTextures(1, &colorTexture_);
	if (depthRenderbuffer_) glDeleteRenderbuffers(1, &depthRenderbuffer_);
	if (fbo_) glDeleteFramebuffers(1, &fbo_);
	colorTexture_ = depthRenderbuffer_ = fbo_ = 0;
	fboWidth_ = fboHeight_ = 0;
}

// Verifies and instantiates an OpenGL Framebuffer Object matched to the target dimensions
void Scene::EnsureFramebuffer(int width, int height) {
	if (fbo_ != 0 && width == fboWidth_ && height == fboHeight_) {
		return;
	}

	DestroyFramebuffer();

	fboWidth_ = width;
	fboHeight_ = height;

	glGenFramebuffers(1, &fbo_);
	glBindFramebuffer(GL_FRAMEBUFFER, fbo_);

	//color attachment
	glGenTextures(1, &colorTexture_);
	glBindTexture(GL_TEXTURE_2D, colorTexture_);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, width, height, 0, GL_RGB, GL_UNSIGNED_BYTE, nullptr);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, colorTexture_, 0);

	//depth attachment
	glGenRenderbuffers(1, &depthRenderbuffer_);
	glBindRenderbuffer(GL_RENDERBUFFER, depthRenderbuffer_);
	glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, width, height);
	glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, depthRenderbuffer_);

	GLenum status = glCheckFramebufferStatus(GL_FRAMEBUFFER);
	if (status != GL_FRAMEBUFFER_COMPLETE) {
		std::cerr << "[Scene] Framebuffer incomplete, status: " << status << std::endl;
	}

	glBindFramebuffer(GL_FRAMEBUFFER, 0);
}


// Binds the custom framebuffer, applies matrix uniforms, and draws the 3D geometry
void Scene::Render(int width, int height) {
	if (width <= 0 || height <= 0) return;

	EnsureFramebuffer(width, height);

	glBindFramebuffer(GL_FRAMEBUFFER, fbo_);
	glViewport(0, 0, width, height);
	glEnable(GL_DEPTH_TEST);
	glClearColor(0.1f, 0.1f, 0.12f, 1.0f);
	glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

	if (model_ && shader_) {
		shader_->Use();

		glm::mat4 view = camera_.GetViewMatrix();
		glm::mat4 proj = camera_.GetProjectionMatrix(static_cast<float>(width) / height);
		glm::mat4 modelMat = model_->GetModelMatrix();

		shader_->SetMat4("view", view);
		shader_->SetMat4("projection", proj);
		shader_->SetMat4("model", modelMat);
		shader_->SetVec3("lightDir", lightDir_);
		shader_->SetFloat("ambientStrength", ambientStrength_);
		shader_->SetVec3("objectColor", objectColor_);
		shader_->SetInt("colorMode", colorMode_);
		model_->Draw(*shader_);
	}

	glBindFramebuffer(GL_FRAMEBUFFER, 0);
}

// Returns the internal OpenGL color texture attachment handle
GLuint Scene::GetColorTexture() {
	return colorTexture_;
}

// Returns a reference to the scene viewport camera
Camera& Scene::GetCamera() {
	return camera_;
}

// Returns a raw pointer to the currently loaded 3D asset model
Model* Scene::GetModel() {
	return model_.get();
}
