#version 330 core
in vec3 Normal;
in vec3 FragPos;
in vec2 TexCoords;
in vec3 VertColor;
out vec4 FragColor;

uniform sampler2D diffuseTexture;
uniform int hasTexture;
uniform vec3 objectColor;
uniform int colorMode;   // 0=auto, 1=vertex color, 2=texture

uniform vec3 lightDir;
uniform float ambientStrength;

void main() {
    vec3 baseColor;
    if (colorMode == 2 && hasTexture == 1) {
        baseColor = texture(diffuseTexture, TexCoords).rgb;
    } else {
        bool hasVertexColor = (VertColor.r + VertColor.g + VertColor.b) < 2.99f;
        if (hasVertexColor)
            baseColor = VertColor;
        else if (hasTexture == 1)
            baseColor = texture(diffuseTexture, TexCoords).rgb;
        else
            baseColor = objectColor;
    }

    vec3 norm = normalize(Normal);
    float diff = max(dot(norm, normalize(-lightDir)), 0.0);
    float lighting = ambientStrength + (1.0 - ambientStrength) * diff;

    // FragColor = vec4(baseColor, 1.0);
    FragColor = vec4(lighting * baseColor, 1.0);
}
