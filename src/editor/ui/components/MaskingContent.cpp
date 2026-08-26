#include "editor/ui/components/MaskingContent.h"

#include "editor/ui/UIStyle.h"

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

    UIStyle::SectionTitle(
        "MASK SELECTION",
        "Choose the candidate that best isolates the subject, or skip this image."
    );
    if (textureId_ != 0) {
        constexpr float framePadding = 8.0f;
        const ImVec2 available = ImGui::GetContentRegionAvail();
        const float maxImageWidth = std::max(1.0f, available.x - framePadding * 2.0f);
        const float scale = std::min(
            maxImageWidth / static_cast<float>(std::max(1, textureWidth_)),
            420.0f / static_cast<float>(std::max(1, textureHeight_))
        );
        const ImVec2 imageSize(textureWidth_ * scale, textureHeight_ * scale);
        const ImVec2 frameSize(
            imageSize.x + framePadding * 2.0f,
            imageSize.y + framePadding * 2.0f
        );
        ImGui::SetCursorPosX(
            ImGui::GetCursorPosX() +
            std::max(0.0f, (available.x - frameSize.x) * 0.5f)
        );

        const ImVec2 framePosition = ImGui::GetCursorScreenPos();
        ImGui::Dummy(frameSize);
        ImDrawList* drawList = ImGui::GetWindowDrawList();
        drawList->AddRectFilled(
            framePosition,
            ImVec2(framePosition.x + frameSize.x, framePosition.y + frameSize.y),
            ImGui::GetColorU32(ImVec4(0.055f, 0.063f, 0.078f, 1.0f)),
            3.0f
        );
        drawList->AddImage(
            static_cast<ImTextureID>(textureId_),
            ImVec2(framePosition.x + framePadding, framePosition.y + framePadding),
            ImVec2(
                framePosition.x + framePadding + imageSize.x,
                framePosition.y + framePadding + imageSize.y
            )
        );
        drawList->AddRect(
            framePosition,
            ImVec2(framePosition.x + frameSize.x, framePosition.y + frameSize.y),
            ImGui::GetColorU32(ImGuiCol_Border),
            3.0f
        );
    } else {
        ImGui::TextDisabled("Preview image unavailable");
    }

    ImGui::Spacing();
    ImGui::BeginDisabled(!selectionEnabled);
    const int safeCandidateCount = std::max(0, candidateCount);
    for (int candidate = 0; candidate < safeCandidateCount; ++candidate) {
        const std::string label = "Candidate " + std::to_string(candidate + 1);
        if (UIStyle::Button(
            label.c_str(),
            UIStyle::ButtonKind::Secondary,
            ImVec2(112.0f, 0.0f)
        )) {
            inputs.push_back({UIClick::SubmitSelection, std::to_string(candidate)});
        }
        if (candidate + 1 < safeCandidateCount) {
            ImGui::SameLine();
        }
    }
    if (safeCandidateCount > 0) {
        ImGui::SameLine();
    }
    if (UIStyle::Button(
        "Skip",
        UIStyle::ButtonKind::Ghost,
        ImVec2(64.0f, 0.0f)
    )) {
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
