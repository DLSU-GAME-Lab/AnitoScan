#include "Scene.h"

#include <glad/gl.h>
#include <iostream>

// Initializes the scene with a default camera position  and creates the default shader used for rendering.
Scene::Scene() : camera(glm::vec3(0.0f, 0.0f, 3.0f), 5.0f) {
	shader = std::make_unique<Shader>("shaders/default.vert", "shaders/default.frag");
}

Scene::~Scene() {}

// Loads a 3D model from file and adjustments on camera
void Scene::LoadModel(const String& objPath) {
	model = std::make_unique<Model>(objPath);
	Recenter();
}

// Recalculates camera distance and target orientation based on the active model's bounds.
void Scene::Recenter() {
	if (!model) return;

	glm::vec3 center = model->GetCentroid();
	float radius = model->GetBoundsRadius();

	float fovRadians = glm::radians(45.0f);
	float distance = (radius / std::sin(fovRadians * 0.5f)) * 1.5f;
	
	camera.SetTarget(center);
	camera.SetDistance(distance);

	std::cout << "[Scene] Recentered camera: target(" << center.x << ", " << center.y << ", " << center.z
		<< ") distance(" << distance << ")\n";
}

// Updates scene transformations, step logics, and animations over time
void Scene::Update(float deltaTime) {}


// Deletes OpenGL color textures, depth renderbuffers, and framebuffers to clear memory
void Scene::DestroyFramebuffer() {
	if (colorTexture) glDeleteTextures(1, &colorTexture);
	if (depthRenderbuffer) glDeleteRenderbuffers(1, &depthRenderbuffer);
	if (fbo) glDeleteFramebuffers(1, &fbo);
	colorTexture = depthRenderbuffer = fbo = 0;
	fboWidth = fboHeight = 0;
}

// Verifies and instantiates an OpenGL Framebuffer Object matched to the target dimensions
void Scene::EnsureFramebuffer(int width, int height) {
	if (fbo != 0 && width == fboWidth && height == fboHeight) {
		return;
	}

	DestroyFramebuffer();

	fboWidth = width;
	fboHeight = height;

	glGenFramebuffers(1, &fbo);
	glBindFramebuffer(GL_FRAMEBUFFER, fbo);

	//color attachment
	glGenTextures(1, &colorTexture);
	glBindTexture(GL_TEXTURE_2D, colorTexture);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, width, height, 0, GL_RGB, GL_UNSIGNED_BYTE, nullptr);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, colorTexture, 0);

	//depth attachment
	glGenRenderbuffers(1, &depthRenderbuffer);
	glBindRenderbuffer(GL_RENDERBUFFER, depthRenderbuffer);
	glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, width, height);
	glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, depthRenderbuffer);

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

	glBindFramebuffer(GL_FRAMEBUFFER, fbo);
	glViewport(0, 0, width, height);
	glEnable(GL_DEPTH_TEST);
	glClearColor(0.1f, 0.1f, 0.12f, 1.0f);
	glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

	if (model && shader) {
		shader->Use();

		glm::mat4 view = camera.GetViewMatrix();
		glm::mat4 proj = camera.GetProjectionMatrix(static_cast<float>(width) / height);
		glm::mat4 modelMat = model->GetModelMatrix();

		shader->SetMat4("view", view);
		shader->SetMat4("projection", proj);
		shader->SetMat4("model", modelMat);
		shader->SetVec3("lightDir", lightDir);
		shader->SetFloat("ambientStrength", ambientStrength);
		shader->SetVec3("objectColor", objectColor);
		shader->SetInt("colorMode", colorMode);
		model->Draw(*shader);
	}

	//temporary
	glBindFramebuffer(GL_READ_FRAMEBUFFER, fbo);
	glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0);
	glBlitFramebuffer(0, 0, width, height, 0, 0, width, height, GL_COLOR_BUFFER_BIT, GL_NEAREST);

	glBindFramebuffer(GL_FRAMEBUFFER, 0);
}

// Returns the internal OpenGL color texture attachment handle
GLuint Scene::GetColorTexture() {
	return this->colorTexture;
}

// Returns a reference to the scene viewport camera
Camera& Scene::GetCamera() {
	return this->camera;
}

// Returns a raw pointer to the currently loaded 3D asset model
Model* Scene::GetModel() {
	return this->model.get();
}
