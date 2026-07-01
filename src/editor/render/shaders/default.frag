#version 330 core

in vec3 Normal;
in vec3 FragPos;
in vec2 TexCoords;
out vec4 FragColor;

uniform vec3 lightDir;
uniform vec3 objectColor;
uniform sampler2D diffuseTexture;
uniform int hasTexture;

void main() {
    vec3 norm = normalize(Normal);
    float diff = max(dot(norm, normalize(-lightDir)), 0.0);

    vec3 baseColor = (hasTexture == 1) ? texture(diffuseTexture, TexCoords).rgb : objectColor;
    vec3 result = (0.4 + diff * 0.8) * baseColor;

    FragColor = vec4(result, 1.0);
}