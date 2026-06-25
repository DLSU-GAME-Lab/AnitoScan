#pragma once

#include <vector>
#include <glad/gl.h>
#include <glm/glm.hpp>
#include "Shader.h"

struct Vertex {
	glm::vec3 Position;
	glm::vec3 Normal;
	glm::vec2 TexCoords;
};

class Mesh {
public:
	Mesh(std::vector<Vertex> vertices, std::vector<unsigned int> indices, GLuint textureID);
	~Mesh();

	void Draw(const Shader& shader) const;
	size_t GetVertexCount();
	size_t GetIndexCount();

private:
	void SetupMesh();
	void ReleaseResources();
		
private:
	GLuint VAO = 0;
	GLuint VBO = 0;
	GLuint EBO = 0;
	std::vector<Vertex> vertices;
	std::vector<unsigned int> indices;
	GLuint textureID = 0;
};