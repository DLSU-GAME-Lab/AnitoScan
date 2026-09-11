#include "Mesh.h"

#include "Shader.h"

#include <cstddef>
#include <utility>

// Initializes mesh data and sets up the corresponding OpenGL buffers and vertex attributes
Mesh::Mesh(std::vector<Vertex> vertices, std::vector<unsigned int> indices, GLuint textureID) {
	vertices_ = std::move(vertices);
	indices_ = std::move(indices);
	textureID_ = textureID;

	SetupMesh();
}

// Clean up
Mesh::~Mesh() {
	ReleaseResources();
}

// Releases all OpenGL buffer and vertex array resources associated with the mesh
void Mesh::ReleaseResources() {
	if (EBO_) glDeleteBuffers(1, &EBO_);
	if (VBO_) glDeleteBuffers(1, &VBO_);
	if (VAO_) glDeleteVertexArrays(1, &VAO_);
	VAO_ = VBO_ = EBO_ = 0;
}

// Generates and configures the VAO, VBO, and EBO.
// Uploads vertex and index data to the GPU and defines vertex attribute layout.
void Mesh::SetupMesh() {
	glGenVertexArrays(1, &VAO_);
	glGenBuffers(1, &VBO_);
	glGenBuffers(1, &EBO_);
	
	//bind vertex array and buffers
	//VAO
	glBindVertexArray(VAO_);

	glBindBuffer(GL_ARRAY_BUFFER, VBO_);
	glBufferData(
		GL_ARRAY_BUFFER,
		vertices_.size() * sizeof(Vertex),
		vertices_.data(),
		GL_STATIC_DRAW
	);

	//EBO
	glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, EBO_);
	glBufferData(GL_ELEMENT_ARRAY_BUFFER,
		indices_.size() * sizeof(unsigned int),
		indices_.data(),
		GL_STATIC_DRAW
	);

	//layout location = 0: vec3 Position
	glEnableVertexAttribArray(0);
	glVertexAttribPointer(
		0, 3,
		GL_FLOAT, GL_FALSE,
		sizeof(Vertex),
		(void*)offsetof(Vertex, Position)
	);

	//layout location = 1: vec3 Normal
	glEnableVertexAttribArray(1);
	glVertexAttribPointer(
		1, 3,
		GL_FLOAT, GL_FALSE,
		sizeof(Vertex),
		(void*)offsetof(Vertex, Normal)
	);

	glEnableVertexAttribArray(2);
	glVertexAttribPointer(
		2, 2,
		GL_FLOAT, GL_FALSE,
		sizeof(Vertex),
		(void*)offsetof(Vertex, TexCoords)
	);

	glEnableVertexAttribArray(3);
	glVertexAttribPointer(
		3, 3,
		GL_FLOAT, GL_FALSE,
		sizeof(Vertex),
		(void*)offsetof(Vertex, Color)
	);

	glBindVertexArray(0);
}

// Renders the mesh using indexed drawing
void Mesh::Draw(const Shader& shader) const {
	if (textureID_ != 0) {
		glActiveTexture(GL_TEXTURE0);
		glBindTexture(GL_TEXTURE_2D, textureID_);
		shader.SetInt("diffuseTexture", 0);
		shader.SetInt("hasTexture", 1);
	}
	else {
		shader.SetInt("hasTexture", 0);
	}

	glBindVertexArray(VAO_);
	glDrawElements(GL_TRIANGLES, static_cast<GLsizei>(indices_.size()), GL_UNSIGNED_INT, nullptr);
	glBindVertexArray(0);
}

// Returns the vertices count of the mesh
size_t Mesh::GetVertexCount() {
	return vertices_.size();
}

// Returns the indices count of the mesh
size_t Mesh::GetIndexCount() {
	return indices_.size();
}