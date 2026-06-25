#include "Mesh.h"

// Initializes mesh data and sets up the corresponding OpenGL buffers and vertex attributes
Mesh::Mesh(std::vector<Vertex> vertices, std::vector<unsigned int> indices, GLuint textureID) {
	this->vertices = std::move(vertices);
	this->indices = std::move(indices);
	this->textureID = textureID;

	SetupMesh();
}

// Clean up
Mesh::~Mesh() {
	ReleaseResources();
}

// Releases all OpenGL buffer and vertex array resources associated with the mesh
void Mesh::ReleaseResources() {
	if (EBO) glDeleteBuffers(1, &EBO);
	if (VBO) glDeleteBuffers(1, &VBO);
	if (VAO) glDeleteVertexArrays(1, &VAO);
	VAO = VBO = EBO = 0;
}

// Generates and configures the VAO, VBO, and EBO.
// Uploads vertex and index data to the GPU and defines vertex attribute layout.
void Mesh::SetupMesh() {
	glGenVertexArrays(1, &VAO);
	glGenBuffers(1, &VBO);
	glGenBuffers(1, &EBO);
	
	//bind vertex array and buffers
	//VAO
	glBindVertexArray(VAO);

	glBindBuffer(GL_ARRAY_BUFFER, VBO);
	glBufferData(
		GL_ARRAY_BUFFER,
		vertices.size() * sizeof(Vertex),
		vertices.data(),
		GL_STATIC_DRAW
	);

	//EBO
	glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, EBO);
	glBufferData(GL_ELEMENT_ARRAY_BUFFER,
		indices.size() * sizeof(unsigned int),
		indices.data(),
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

	glBindVertexArray(0);
}

// Renders the mesh using indexed drawing
void Mesh::Draw(const Shader& shader) const {
	if (textureID != 0) {
		glActiveTexture(GL_TEXTURE0);
		glBindTexture(GL_TEXTURE_2D, textureID);
		shader.SetInt("diffuseTexture", 0);
		shader.SetInt("hasTexture", 1);
	}
	else {
		shader.SetInt("hasTexture", 0);
	}

	glBindVertexArray(VAO);
	glDrawElements(GL_TRIANGLES, static_cast<GLsizei>(indices.size()), GL_UNSIGNED_INT, nullptr);
	glBindVertexArray(0);
}

size_t Mesh::GetVertexCount() {
	return this->vertices.size();
}
size_t Mesh::GetIndexCount() {
	return this->indices.size();
}