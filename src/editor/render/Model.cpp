#include "Model.h"

#include <iostream>
#include <unordered_map>
#include <glm/gtc/matrix_transform.hpp>

#define TINYOBJLOADER_IMPLEMENTATION
#define TINYOBJLOADER_DISABLE_FAST_FLOAT
#include "tiny_obj_loader.h"

#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"

namespace {
	struct IndexKey {
		int posIdx, normIdx, uvIdx;
		bool operator==(const IndexKey& o) const {
			return posIdx == o.posIdx && normIdx == o.normIdx && uvIdx == o.uvIdx;
		}
	};
	struct IndexKeyHash {
		size_t operator()(const IndexKey& k) const {
			return std::hash<long long>()(
				(static_cast<long long>(k.posIdx) << 42) ^
				(static_cast<long long>(k.normIdx) << 21) ^
				static_cast<long long>(k.uvIdx));
		}
	};
}

Model::Model(const String& objPath) {
	LoadOBJ(objPath);
}

Model::~Model() {}

void Model::LoadOBJ(const String& objPath) {
	size_t slash = objPath.find_last_of("/\\");
	this->directory = (slash == std::string::npos) ? "." : objPath.substr(0, slash);

	tinyobj::attrib_t attrib;
	std::vector<tinyobj::shape_t> shapes;
	std::vector<tinyobj::material_t> materials;
	String warning, error;

	bool success = tinyobj::LoadObj(
		&attrib, &shapes, &materials,
		&warning, &error,
		objPath.c_str(),
		(this->directory + "/").c_str()
	);

	if (!warning.empty())
		std::cerr << "[WARNING]: " << warning << std::endl;

	if (!error.empty())
		std::cerr << "[ERROR]: " << error << std::endl;

	if (!success) {
		std::cerr << "[ERROR]: Failed to load model: " << objPath << std::endl;
		return;
	}

	std::unordered_map<int, std::vector<Vertex>> vertsByMat;
	std::unordered_map<int, std::vector<unsigned int>> indicesByMat;
	std::unordered_map<int, std::unordered_map<IndexKey, unsigned int, IndexKeyHash>> dedupByMat;

	for (const auto& shape : shapes) {
		size_t indexoffset = 0;
		for (size_t f = 0; f < shape.mesh.num_face_vertices.size(); f++) {
			int fv = shape.mesh.num_face_vertices[f];
			int matID = shape.mesh.material_ids.empty() ? -1 : shape.mesh.material_ids[f];
		
			for (int v = 0; v < fv; v++) {
				tinyobj::index_t idx = shape.mesh.indices[indexoffset + v];

				IndexKey key{ idx.vertex_index, idx.normal_index, idx.texcoord_index };
				auto& dedup = dedupByMat[matID];
				auto it = dedup.find(key);

				if (it != dedup.end()) {
					indicesByMat[matID].push_back(it->second);
					continue;
				}

				Vertex vert{};
				vert.Position = {
					attrib.vertices[3 * idx.vertex_index + 0],
					attrib.vertices[3 * idx.vertex_index + 1],
					attrib.vertices[3 * idx.vertex_index + 2]
				};

				if (idx.normal_index >= 0) {
					vert.Normal = {
						attrib.normals[3 * idx.normal_index + 0],
						attrib.normals[3 * idx.normal_index + 1],
						attrib.normals[3 * idx.normal_index + 2]
					};
				}
				else {
					vert.Normal = { 0.0f, 1.0f, 0.0f };
				}

				if (idx.texcoord_index >= 0) {
					vert.TexCoords = {
						attrib.texcoords[2 * idx.texcoord_index + 0],
						attrib.texcoords[2 * idx.texcoord_index + 1]
					};
				}
				else {
					vert.TexCoords = { 0.0f, 0.0f };
				}

				unsigned int newIndex = static_cast<unsigned int>(vertsByMat[matID].size());
				vertsByMat[matID].push_back(vert);
				indicesByMat[matID].push_back(newIndex);
				dedup[key] = newIndex;
			}
			indexoffset += fv;
		}
	}

	for (auto& [matID, verts] : vertsByMat) {
		GLuint texID = 0;
		if (matID >= 0 && matID < static_cast<int>(materials.size())) {
			const String& diffuseTex = materials[matID].diffuse_texname;
			if (!diffuseTex.empty()) {
				texID = LoadTexture(diffuseTex);
			}
		}
		this->meshes.emplace_back(std::move(verts), std::move(indicesByMat[matID]), texID);
	}

	std::cout << "Loaded (" << objPath << ") size: " << meshes.size() << std::endl;



	//bounding box
	glm::vec3 boundsMin(FLT_MAX), boundsMaxLocal(-FLT_MAX);
	glm::dvec3 sum(0.0);
	size_t vertCount = attrib.vertices.size() / 3;
	for (size_t i = 0; i < attrib.vertices.size(); i += 3) {
		glm::vec3 v(attrib.vertices[i], attrib.vertices[i + 1], attrib.vertices[i + 2]);
		boundsMin = glm::min(boundsMin, v);
		boundsMaxLocal = glm::max(boundsMaxLocal, v);
		sum += glm::dvec3(v);
	}

	this->boundsMin = boundsMin;
	this->boundsMax = boundsMaxLocal;
	this->GetCenter() = vertCount > 0 ? glm::vec3(sum / static_cast<double>(vertCount)) : glm::vec3(0.0f);

	//std::cout << "[Model] Bounding box min(" << boundsMin.x << ", " << boundsMin.y << ", " << boundsMin.z
	//	<< ") max(" << boundsMaxLocal.x << ", " << boundsMaxLocal.y << ", " << boundsMaxLocal.z << ")\n";
	//std::cout << "[Model] Centroid (" << center.x << ", " << center.y << ", " << center.z << ")\n";
}

GLuint Model::LoadTexture(const String& filename) {
	auto cached = this->textureCache.find(filename);
	if (cached != this->textureCache.end())
		return cached->second;
	
	String fullPath = this->directory + "/" + filename;
	int width, height, channels;
	stbi_set_flip_vertically_on_load(true);
	unsigned char* data = stbi_load(fullPath.c_str(), &width, &height, &channels, 0);
	if (!data) {
		std::cerr << "[ERROR]: Failed to load model's texture" << fullPath << std::endl;
		return 0;
	}

	GLenum format = (channels == 1) ? GL_RED : (channels == 3) ? GL_RGB : GL_RGBA;
	GLuint texID;
	glGenTextures(1, &texID);
	glBindTexture(GL_TEXTURE_2D, texID);
	glTexImage2D(GL_TEXTURE_2D, 0, format, width, height, 0, format, GL_UNSIGNED_BYTE, data);
	glGenerateMipmap(GL_TEXTURE_2D);

	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	
	stbi_image_free(data);

	textureCache[filename] = texID;
	return texID;
}

glm::mat4 Model::GetModelMatrix() const {
	glm::mat4 m = glm::translate(glm::mat4(1.0f), position);
	m = glm::rotate(m, glm::radians(rotation.x), glm::vec3(1, 0, 0));
	m = glm::rotate(m, glm::radians(rotation.y), glm::vec3(0, 1, 0));
	m = glm::rotate(m, glm::radians(rotation.z), glm::vec3(0, 0, 1));
	m = glm::scale(m, scale);
	return m;
}

void Model::Draw(const Shader& shader) const {
	for (const auto& mesh : this->meshes) {
		mesh.Draw(shader);
	}
}

void Model::SetPosition(glm::vec3 position) {
	this->position = position;
}

void Model::SetRotation(glm::vec3 euler) {
	this->rotation = euler;
}

void Model::SetScale(glm::vec3 scale) {
	this->scale = scale;
}

glm::vec3 Model::GetPosition() {
	return this->position;
}

size_t Model::GetMeshCount() {
	return this->meshes.size();
}

glm::vec3 Model::GetBoundsCenter() {
	return (this->boundsMin + this->boundsMax) * 0.5f;
}

float Model::GetBoundsRadius() {
	return glm::length(this->boundsMax - this->boundsMin) * 0.5f;
}

glm::vec3 Model::GetCenter() {
	return this->center;
}