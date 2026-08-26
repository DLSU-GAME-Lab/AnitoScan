#include "editor/ui/components/MaskingContent.h"

#include <algorithm>
#include <string>

#include <glad/gl.h>
#include <imgui.h>

#include <stb_image.h>

void MaskingContent::Render(
    const std::string& previewPath,
    int candidateCount,
    bool selectionEnabled,
    std::vector<UIInput>& inputs
) {
    if (previewPath.empty()) {
        Shutdown();
        return;
    }

    if (previewPath != loadedPath_) {
        LoadPreview(previewPath.c_str());
    }

    ImGui::TextUnformatted("Mask selection");
    ImGui::Spacing();
    if (textureId_ != 0) {
        const ImVec2 available = ImGui::GetContentRegionAvail();
        const float scale = std::min(available.x / textureWidth_, 420.0f / textureHeight_);
        const ImVec2 imageSize(textureWidth_ * scale, textureHeight_ * scale);
        ImGui::SetCursorPosX(ImGui::GetCursorPosX() + std::max(0.0f, (available.x - imageSize.x) * 0.5f));
        ImGui::Image(static_cast<ImTextureID>(textureId_), imageSize);
    } else {
        ImGui::TextDisabled("Preview image unavailable");
    }

    ImGui::Spacing();
    ImGui::BeginDisabled(!selectionEnabled);
    const int safeCandidateCount = std::max(0, candidateCount);
    for (int candidate = 0; candidate < safeCandidateCount; ++candidate) {
        const std::string label = "Candidate " + std::to_string(candidate + 1);
        if (ImGui::Button(label.c_str())) {
            inputs.push_back({UIClick::SubmitSelection, std::to_string(candidate)});
        }
        if (candidate + 1 < safeCandidateCount) {
            ImGui::SameLine();
        }
    }
    if (safeCandidateCount > 0) {
        ImGui::SameLine();
    }
    if (ImGui::Button("Skip")) {
        inputs.push_back({UIClick::SubmitSelection, "-1"});
    }
    ImGui::EndDisabled();
}

void MaskingContent::Shutdown() {
    if (textureId_ != 0) {
        glDeleteTextures(1, &textureId_);
        textureId_ = 0;
    }
    textureWidth_ = 0;
    textureHeight_ = 0;
    loadedPath_.clear();
}

bool MaskingContent::LoadPreview(const char* path) {
    Shutdown();
    loadedPath_ = path;

    int channels = 0;
    stbi_uc* pixels = stbi_load(path, &textureWidth_, &textureHeight_, &channels, 4);
    if (pixels == nullptr) {
        return false;
    }

    glGenTextures(1, &textureId_);
    glBindTexture(GL_TEXTURE_2D, textureId_);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, textureWidth_, textureHeight_, 0, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glBindTexture(GL_TEXTURE_2D, 0);
    stbi_image_free(pixels);
    return true;
}
