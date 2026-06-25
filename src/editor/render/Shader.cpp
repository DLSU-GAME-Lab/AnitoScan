#include "Shader.h"

// Loads shader source files, compiles fragment and vertex shader and links them to a shader program
Shader::Shader(const String& vertPath, const String& fragPath) {
	String rootPath = "src/editor/render/";
	String vertSrc = LoadFile(rootPath + vertPath);
	String fragSrc = LoadFile(rootPath + fragPath);

	GLuint vertShader = CompileShader(vertSrc, GL_VERTEX_SHADER, vertPath);
	GLuint fragShader = CompileShader(fragSrc, GL_FRAGMENT_SHADER, fragPath);

	this->programID = glCreateProgram();
	glAttachShader(this->programID, vertShader);
	glAttachShader(this->programID, fragShader);
	glLinkProgram(this->programID);

	GLint success;
	glGetProgramiv(this->programID, GL_LINK_STATUS, &success);
	if (!success) {
		char infoLog[1024];
		glGetProgramInfoLog(this->programID, 1024, nullptr, infoLog);
		std::cerr << "[ERROR]: Shader Link error (" << vertPath << " / " << fragPath << ") : \n"
				  << infoLog << std::endl;
	}

	glDeleteShader(vertShader);
	glDeleteShader(fragShader);
}

// Clean up
Shader::~Shader() {
	if (this->programID != 0) {
		glDeleteProgram(this->programID);
	}
}

// Loads the contents of a shader file into a string
String Shader::LoadFile(const String& path){
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
GLuint Shader::CompileShader(const String& src, GLenum type, const String& debugName) {
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
GLint Shader::GetUniformLocation(const String& name) const {
	static thread_local std::unordered_map<GLuint, std::unordered_map<String, GLint>> cache;
	auto& progCache = cache[this->programID];
	auto it = progCache.find(name);
	if (it != progCache.end())
		return it->second;

	GLint loc = glGetUniformLocation(this->programID, name.c_str());
	if (loc == -1) {
		std::cerr << "[WARNING]: uniform (" << name << ") not found" << std::endl;
	}
	progCache[name] = loc;
	return loc;
}

// Activates shader program for rendering
void Shader::Use() {
	glUseProgram(this->programID);
}

void Shader::SetMat4(const String& name, const glm::mat4& mat) const {
	glUniformMatrix4fv(
		GetUniformLocation(name),
		1,
		GL_FALSE,
		&mat[0][0]
	);
}

void Shader::SetVec3(const String& name, const glm::vec3& vec) const {
	glUniform3fv(
		GetUniformLocation(name),
		1,
		&vec[0]
	);
}

void Shader::SetFloat(const String& name, float value) const{
	glUniform1f(GetUniformLocation(name), value);
}

void Shader::SetInt(const String& name, int value) const{
	glUniform1i(GetUniformLocation(name), value);
}

// Returns the OpenGL program ID associated with this shader
GLuint Shader::GetID() const {
	return this->programID;
}