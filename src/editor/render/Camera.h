#pragma once

#include <glm/glm.hpp>
#include <glm/gtc/quaternion.hpp>

class Camera {
public:
	Camera(glm::vec3 target, float distance);
	~Camera();

	void ProcessMouseDrag(float dx, float dy);
	void ProcessKeyboard(bool left, bool right, bool up, bool down, float deltaTime);

	void ProcessScroll(float delta);
	void ProcessPan(float dx, float dy);

	void SetTarget(glm::vec3 target);
	void SetDistance(float distance);
	glm::vec3 GetPosition();
	glm::mat4 GetViewMatrix();
	glm::mat4 GetProjectionMatrix(float aspectRatio);

private:
	glm::vec3 target_ = glm::vec3(0.0f);
	float distance_ = 5.0f;

	glm::quat orientation_{ 1.0f, 0.0f, 0.0f, 0.0f };

	float fov_ = 45.0f;
	float nearPlane_ = 0.1f;
	float farPlane_ = 100.0f;

	float orbitSensitivity_ = 0.3f;
	float zoomSensitivity_ = 0.5f;
	float panSensitivity_ = 0.003f;
	float minDistance_ = 0.5f;
	float maxDistance_ = 50.0f;
};