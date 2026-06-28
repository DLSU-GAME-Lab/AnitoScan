#pragma once

#include <glm/glm.hpp>
#include <glad/gl.h>
#include <fstream>
#include <sstream>
#include <iostream>
#include <unordered_map>

#include "../Types.h"


// Contains helper functions for shaders
class Shader {
public:
	Shader(const String& vertPath, const String& fragPath);
	~Shader();

	Shader(const Shader&) = delete;
	Shader& operator=(const Shader&) = delete;

	void Use();
	void SetMat4(const String& name, const glm::mat4& mat) const;
	void SetVec3(const String& name, const glm::vec3& vec) const;
	void SetFloat(const String& name, float value) const;
	void SetInt(const String& name, int value) const;

	GLuint GetID() const;

private:
	GLuint CompileShader(const String& src, GLenum type, const String& debugName);
	String LoadFile(const String& path);
	GLint GetUniformLocation(const String& name) const;

private:
	GLuint programID = 0;


};