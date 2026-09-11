#pragma once

#include <cstddef>
#include <vector>
#include <glad/gl.h>
#include <glm/glm.hpp>

class Shader;

struct Vertex {
	glm::vec3 Position;
	glm::vec3 Normal;
	glm::vec2 TexCoords;
	glm::vec3 Color;
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
	GLuint VAO_ = 0;
	GLuint VBO_ = 0;
	GLuint EBO_ = 0;
	std::vector<Vertex> vertices_;
	std::vector<unsigned int> indices_;
	GLuint textureID_ = 0;
};