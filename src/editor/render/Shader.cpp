#include "Shader.h"

#include <fstream>
#include <iostream>
#include <sstream>
#include <unordered_map>

// Loads shader source files, compiles fragment and vertex shader and links them to a shader program
Shader::Shader(const std::string& vertPath, const std::string& fragPath) {
	std::string rootPath = std::string(PROJECT_ROOT_DIR) + "/src/editor/render/";

	std::cout << rootPath << std::endl;
	std::string vertSrc = LoadFile(rootPath + vertPath);
	std::string fragSrc = LoadFile(rootPath + fragPath);

	GLuint vertShader = CompileShader(vertSrc, GL_VERTEX_SHADER, vertPath);
	GLuint fragShader = CompileShader(fragSrc, GL_FRAGMENT_SHADER, fragPath);

	programID_ = glCreateProgram();
	glAttachShader(programID_, vertShader);
	glAttachShader(programID_, fragShader);
	glLinkProgram(programID_);

	GLint success;
	glGetProgramiv(programID_, GL_LINK_STATUS, &success);
	if (!success) {
		char infoLog[1024];
		glGetProgramInfoLog(programID_, 1024, nullptr, infoLog);
		std::cerr << "[ERROR]: Shader Link error (" << vertPath << " / " << fragPath << ") : \n"
				  << infoLog << std::endl;
	}

	glDeleteShader(vertShader);
	glDeleteShader(fragShader);
}

// Clean up
Shader::~Shader() {
	if (programID_ != 0) {
		glDeleteProgram(programID_);
	}
}

// Loads the contents of a shader file into a string
std::string Shader::LoadFile(const std::string& path){
	std::ifstream file(path);
	if (!file.is_open()) {
		std::cerr << "[ERROR]: Failed to open shader file: " << path << std::endl;
		return "";
	}

	std::stringstream ss;
	ss << file.rdbuf();
	return ss.str();
}

// Helper function for compiling a shader from source code
GLuint Shader::CompileShader(const std::string& src, GLenum type, const std::string& debugName) {
	GLuint shader = glCreateShader(type);
	const char* csrc = src.c_str();
	glShaderSource(shader, 1, &csrc, nullptr);
	glCompileShader(shader);

	GLint success;
	glGetShaderiv(shader, GL_COMPILE_STATUS, &success);
	if (!success) {
		char infoLog[1024];
		glGetShaderInfoLog(shader, 1024, nullptr, infoLog);
		std::cerr << "[ERROR]: Shader compile error (" << debugName << "):\n" << infoLog << std::endl;
	}
	return shader;
}

// Retrieves the location of a uniform variable from the shader program
GLint Shader::GetUniformLocation(const std::string& name) const {
	static thread_local std::unordered_map<GLuint, std::unordered_map<std::string, GLint>> cache;
	auto& progCache = cache[programID_];
	auto it = progCache.find(name);
	if (it != progCache.end())
		return it->second;

	GLint loc = glGetUniformLocation(programID_, name.c_str());
	if (loc == -1) {
		std::cerr << "[WARNING]: uniform (" << name << ") not found" << std::endl;
	}
	progCache[name] = loc;
	return loc;
}

// Activates shader program for rendering
void Shader::Use() {
	glUseProgram(programID_);
}

// Sets a 4x4 matrix uniform in the shader program
void Shader::SetMat4(const std::string& name, const glm::mat4& mat) const {
	glUniformMatrix4fv(
		GetUniformLocation(name),
		1,
		GL_FALSE,
		&mat[0][0]
	);
}

// Sets a 3-component vector uniform in the shader program
void Shader::SetVec3(const std::string& name, const glm::vec3& vec) const {
	glUniform3fv(
		GetUniformLocation(name),
		1,
		&vec[0]
	);
}

// Sets a float point in the shader program
void Shader::SetFloat(const std::string& name, float value) const{
	glUniform1f(GetUniformLocation(name), value);
}

// Sets a singular integer in the shader program
void Shader::SetInt(const std::string& name, int value) const{
	glUniform1i(GetUniformLocation(name), value);
}

// Returns the OpenGL program ID associated with this shader
GLuint Shader::GetID() const {
	return programID_;
}