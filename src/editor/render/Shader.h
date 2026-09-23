#pragma once

#include <string>
#include <glad/gl.h>
#include <glm/glm.hpp>


// Contains helper functions for shaders
class Shader {
public:
	Shader(const std::string& vertPath, const std::string& fragPath);
	~Shader();

	Shader(const Shader&) = delete;
	Shader& operator=(const Shader&) = delete;

	void Use();
	void SetMat4(const std::string& name, const glm::mat4& mat) const;
	void SetVec3(const std::string& name, const glm::vec3& vec) const;
	void SetFloat(const std::string& name, float value) const;
	void SetInt(const std::string& name, int value) const;

	GLuint GetID() const;

private:
	GLuint CompileShader(const std::string& src, GLenum type, const std::string& debugName);
	std::string LoadFile(const std::string& path);
	GLint GetUniformLocation(const std::string& name) const;

private:
	GLuint programID_ = 0;


};