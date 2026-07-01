#include "Camera.h"

#include <glm/gtc/matrix_transform.hpp>
#include <algorithm>

// Sets the target and the distance of the camera from it
Camera::Camera(glm::vec3 target, float distance) {
	this->target = target;
	this->distance = distance;
}

Camera::~Camera() {}

glm::vec3 Camera::GetPosition() {
	glm::vec3 baseOffset(0.0f, 0.0f, distance);
	return target + orientation * baseOffset;
}

// Computes for the view matrix
glm::mat4 Camera::GetViewMatrix() {
	glm::vec3 position = GetPosition();

	glm::vec3 forward = orientation * glm::vec3(0.0f, 0.0f, -1.0f);
	glm::vec3 up = orientation * glm::vec3(0.0f, 1.0f, 0.0f);

	return glm::lookAt(position, position + forward, up);
}

// Computes for the projection matrix
glm::mat4 Camera::GetProjectionMatrix(float aspectRatio) {
	return glm::perspective(glm::radians(fov), aspectRatio, nearPlane, farPlane);
}

// Mouse controls for controlling the orbital movement of the camera
void Camera::ProcessMouseDrag(float dx, float dy) {
	if (dx == 0.0f && dy == 0.0f) return;

	float yawAngle = glm::radians(dx * orbitSensitivity);
	float pitchAngle = glm::radians(-dy * orbitSensitivity);

	glm::vec3 localRight = orientation * glm::vec3(1.0f, 0.0f, 0.0f);
	glm::vec3 localUp = orientation * glm::vec3(0.0f, 1.0f, 0.0f);

	glm::vec3 combinedAxisAngle = localUp * yawAngle + localRight * pitchAngle;
	float angle = glm::length(combinedAxisAngle);

	if (angle > 0.0f) {
		glm::vec3 axis = combinedAxisAngle / angle;
		glm::quat rotation = glm::angleAxis(angle, axis);
		orientation = glm::normalize(rotation * orientation);
	}
}

// Adjusts distance from the model
void Camera::ProcessScroll(float delta) {
	distance -= delta * zoomSensitivity;
	distance = std::clamp(distance, minDistance, maxDistance);
}

void Camera::ProcessPan(float dx, float dy) {
	glm::vec3 localRight = orientation * glm::vec3(1.0f, 0.0f, 0.0f);
	glm::vec3 localUp = orientation * glm::vec3(0.0f, 1.0f, 0.0f);

	float scale = distance * panSensitivity;

	target += (-dx * localRight + dy * localUp) * scale;
}

void Camera::SetTarget(glm::vec3 target) {
	this->target = target;
}

void Camera::SetDistance(float distance) {
	this->distance = std::max(distance, 0.01f);
}