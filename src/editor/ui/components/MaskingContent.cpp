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
        "Choose the best candidate or skip this image. Hover over the preview to magnify details."
    );
    if (textureId_ != 0) {
        constexpr float framePadding = 8.0f;
        constexpr float maxImageHeight = 640.0f;
        const ImVec2 available = ImGui::GetContentRegionAvail();
        const float maxImageWidth = std::max(1.0f, available.x - framePadding * 2.0f);
        const float scale = std::min(
            maxImageWidth / static_cast<float>(std::max(1, textureWidth_)),
            maxImageHeight / static_cast<float>(std::max(1, textureHeight_))
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
        const ImVec2 imageMin(
            framePosition.x + framePadding,
            framePosition.y + framePadding
        );
        const ImVec2 imageMax(
            imageMin.x + imageSize.x,
            imageMin.y + imageSize.y
        );
        drawList->AddImage(
            static_cast<ImTextureID>(textureId_),
            imageMin,
            imageMax
        );
        drawList->AddRect(
            framePosition,
            ImVec2(framePosition.x + frameSize.x, framePosition.y + frameSize.y),
            ImGui::GetColorU32(ImGuiCol_Border),
            3.0f
        );

        if (ImGui::IsMouseHoveringRect(imageMin, imageMax)) {
            constexpr float zoom = 4.0f;
            const ImVec2 magnifierSize(420.0f, 280.0f);
            const ImVec2 mousePosition = ImGui::GetIO().MousePos;
            const float cursorU = std::clamp(
                (mousePosition.x - imageMin.x) / std::max(1.0f, imageSize.x),
                0.0f,
                1.0f
            );
            const float cursorV = std::clamp(
                (mousePosition.y - imageMin.y) / std::max(1.0f, imageSize.y),
                0.0f,
                1.0f
            );
            const float halfU = std::min(
                0.5f,
                magnifierSize.x / (2.0f * zoom * static_cast<float>(std::max(1, textureWidth_)))
            );
            const float halfV = std::min(
                0.5f,
                magnifierSize.y / (2.0f * zoom * static_cast<float>(std::max(1, textureHeight_)))
            );
            const float centerU = std::clamp(cursorU, halfU, 1.0f - halfU);
            const float centerV = std::clamp(cursorV, halfV, 1.0f - halfV);

            ImGui::BeginTooltip();
            ImGui::TextDisabled("4x zoom");
            ImGui::Image(
                static_cast<ImTextureID>(textureId_),
                magnifierSize,
                ImVec2(centerU - halfU, centerV - halfV),
                ImVec2(centerU + halfU, centerV + halfV)
            );
            ImGui::EndTooltip();
        }
    } else {
        ImGui::TextDisabled("Preview image unavailable");
    }

    ImGui::Spacing();
    ImGui::BeginDisabled(!selectionEnabled);
    const int safeCandidateCount = std::max(0, candidateCount);
    for (int candidate = 0; candidate < safeCandidateCount; ++candidate) {
        const std::string label = "Candidate " + std::to_string(candidate);
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
