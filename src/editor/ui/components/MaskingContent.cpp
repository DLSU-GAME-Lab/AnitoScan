#include "editor/ui/components/MaskingContent.h"

#include "editor/controller/PipelineController.h"
#include "editor/domain/RunState.h"

#include <algorithm>

#include <optional>
#include <string>

#include <glad/gl.h>
#include <imgui.h>

#define STB_IMAGE_STATIC
#define STB_IMAGE_IMPLEMENTATION
#include <stb_image.h>

void MaskingContent::Render(const RunState& run, PipelineController& controller) {
    if (!run.selectionRequest) {
        Shutdown();
        return;
    }

    const SelectionRequest& request = *run.selectionRequest;
    const std::string previewPath = request.previewPath.string();
    if (previewPath != loadedPath_) {
        LoadPreview(previewPath.c_str());
    }

    ImGui::Separator();
    ImGui::Text("Frame: %s", request.frame.c_str());

    if (textureId_ != 0) {
        const ImVec2 available = ImGui::GetContentRegionAvail();
        const float scale = std::min(available.x / textureWidth_, 360.0f / textureHeight_);
        const ImVec2 size(textureWidth_ * scale, textureHeight_ * scale);
        ImGui::Image(
            static_cast<ImTextureID>(textureId_),
            size
        );
    } else {
        ImGui::TextDisabled("Preview image unavailable");
    }

    const int candidateCount = std::max(0, request.candidateCount);
    for (int candidate = 0; candidate < candidateCount; ++candidate) {
        const std::string label = "Candidate " + std::to_string(candidate);
        if (ImGui::Button(label.c_str())) {
            controller.SubmitSelection(run.id, candidate);
        }
        if (candidate + 1 < candidateCount) {
            ImGui::SameLine();
        }
    }

    if (ImGui::Button("Skip")) {
        controller.SubmitSelection(run.id, std::nullopt);
    }
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
    glTexImage2D(
        GL_TEXTURE_2D,
        0,
        GL_RGBA,
        textureWidth_,
        textureHeight_,
        0,
        GL_RGBA,
        GL_UNSIGNED_BYTE,
        pixels
    );
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glBindTexture(GL_TEXTURE_2D, 0);
    stbi_image_free(pixels);
    return true;
}
