#pragma once

#include <cstddef>
#include <string>
#include <unordered_map>
#include <vector>
#include <glad/gl.h>
#include <glm/glm.hpp>

class Mesh;
class Shader;

class Model {
public:
	Model(const std::string& objPath);
	~Model();

	void Draw(const Shader& shader) const;
	glm::mat4 GetModelMatrix() const;

	void SetPosition(glm::vec3 position);
	void SetRotation(glm::vec3 euler);
	void SetScale(glm::vec3 scale);

	glm::vec3 GetPosition();
	size_t GetMeshCount();

	glm::vec3 GetBoundsCenter();
	float GetBoundsRadius();
	glm::vec3 GetCentroid();

private:
	void LoadOBJ(const std::string& path);
	GLuint LoadTexture(const std::string& filename);

private:
	std::vector<Mesh> meshes_;
	glm::vec3 position_{ 0.0f };
	glm::vec3 rotation_{ 0.0f };
	glm::vec3 scale_{ 1.0f };

	glm::vec3 boundsMin_{ 0.0f };
	glm::vec3 boundsMax_{ 0.0f };
	glm::vec3 centroid_{ 0.0f };

	std::string directory_;
	std::unordered_map<std::string, GLuint> textureCache_;
};