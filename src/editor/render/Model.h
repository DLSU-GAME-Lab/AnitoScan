#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <glm/glm.hpp>

#include "Shader.h"
#include "Mesh.h"
#include "../Types.h"

class Model {
public:
	Model(const String& objPath);
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
	void LoadOBJ(const String& path);
	GLuint LoadTexture(const String& filename);

private:
	std::vector<Mesh> meshes;
	glm::vec3 position{ 0.0f };
	glm::vec3 rotation{ 0.0f };
	glm::vec3 scale{ 1.0f };

	glm::vec3 boundsMin{ 0.0f };
	glm::vec3 boundsMax{ 0.0f };
	glm::vec3 centroid{ 0.0f };

	String directory;
	std::unordered_map<String, GLuint> textureCache;
};