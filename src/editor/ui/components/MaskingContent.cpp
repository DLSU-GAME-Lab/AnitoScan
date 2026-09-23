#include "editor/ui/components/MaskingContent.h"

#include "editor/ui/UIStyle.h"
#include "editor/controller/ControllerTypes.h"

#include <algorithm>
#include <string>
#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>

#include <glad/gl.h>
#include <imgui.h>

#include <stb_image.h>

void MaskingContent::Render(
    const PhaseDisplayData& data,
    std::vector<UIInput>& inputs
) {
    UpdateInteraction(data);
    const bool selectionEnabled = data.maskSelectionEnabled && !data.selectionSubmitting;
    const int candidateCount = data.candidateCount;
    if (data.previewPath != loadedPath_) {
        if (data.previewPath.empty()) {
            Shutdown();
        } else {
            LoadPreview(data.previewPath.c_str());
        }
    }
    const bool customEnabled = selectionEnabled && textureId_ != 0 &&
        data.imageWidth > 0 && data.imageHeight > 0;
    if (!customEnabled) {
        ResetInteraction();
    }

    UIStyle::SectionTitle(
        "MASK SELECTION",
        candidateCount > 0
            ? "Choose a candidate, draw a custom box, or skip this image. Hover over the preview to magnify details."
            : "No candidates found. Draw a custom box around the subject, or skip this image."
    );
    if (data.selectionSubmitting) {
        ImGui::TextWrapped("Submitting selection...");
    }
    if (!data.selectionError.empty()) {
        ImGui::TextWrapped("%s", data.selectionError.c_str());
    }
    ImGui::BeginDisabled(!customEnabled);
    if (!drawingMode_) {
        if (UIStyle::Button("Draw custom box", UIStyle::ButtonKind::Secondary)) {
            drawingMode_ = true;
        }
    } else {
        if (UIStyle::Button("Exit drawing mode", UIStyle::ButtonKind::Ghost)) {
            ResetInteraction();
        }
        ImGui::SameLine();
        if (UIStyle::Button("Clear", UIStyle::ButtonKind::Ghost)) {
            ResetInteraction();
            drawingMode_ = true;
        }
        ImGui::SameLine();
        ImGui::BeginDisabled(!hasBox_ || dragging_);
        if (UIStyle::Button("Use custom box", UIStyle::ButtonKind::Primary)) {
            std::ostringstream payload;
            payload.imbue(std::locale::classic());
            payload << std::setprecision(std::numeric_limits<double>::max_digits10)
                    << "bbox\n" << boxX1_ << '\n' << boxY1_ << '\n'
                    << boxX2_ << '\n' << boxY2_;
            inputs.push_back({UIClick::SubmitSelection, payload.str()});
            ResetInteraction();
        }
        ImGui::EndDisabled();
    }
    ImGui::EndDisabled();
    if (drawingMode_) {
        ImGui::TextWrapped("Left-drag around the subject. Drag again to replace the box, then choose Use custom box.");
    } else if (textureId_ != 0 && (data.imageWidth <= 0 || data.imageHeight <= 0)) {
        ImGui::TextDisabled("Custom boxes require source image dimensions.");
    }
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
        const ImVec2 afterFrame = ImGui::GetCursorScreenPos();
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

        ImGui::SetCursorScreenPos(imageMin);
        ImGui::BeginDisabled(!customEnabled || !drawingMode_);
        ImGui::InvisibleButton("##CustomBoxImage", imageSize, ImGuiButtonFlags_MouseButtonLeft);
        if (drawingMode_ && customEnabled) {
            const ImVec2 mouse = ImGui::GetIO().MousePos;
            const double sourceX = std::clamp(
                static_cast<double>(mouse.x - imageMin.x) / imageSize.x, 0.0, 1.0
            ) * data.imageWidth;
            const double sourceY = std::clamp(
                static_cast<double>(mouse.y - imageMin.y) / imageSize.y, 0.0, 1.0
            ) * data.imageHeight;
            if (ImGui::IsItemActivated()) {
                anchorX_ = sourceX;
                anchorY_ = sourceY;
                boxX1_ = boxX2_ = sourceX;
                boxY1_ = boxY2_ = sourceY;
                dragging_ = true;
                hasBox_ = false;
                passedDragThreshold_ = false;
            }
            // Keep tracking outside the image; only the initial press needs a clipped hit.
            if (dragging_) {
                passedDragThreshold_ = passedDragThreshold_ ||
                    ImGui::IsMouseDragging(ImGuiMouseButton_Left, 3.0f);
                boxX1_ = std::min(anchorX_, sourceX);
                boxY1_ = std::min(anchorY_, sourceY);
                boxX2_ = std::max(anchorX_, sourceX);
                boxY2_ = std::max(anchorY_, sourceY);
                if (!ImGui::IsMouseDown(ImGuiMouseButton_Left)) {
                    dragging_ = false;
                    hasBox_ = passedDragThreshold_ &&
                        boxX2_ - boxX1_ >= 1.0 && boxY2_ - boxY1_ >= 1.0;
                }
            }
            if (dragging_ || hasBox_) {
                const ImVec2 boxMin(
                    imageMin.x + static_cast<float>(boxX1_ / data.imageWidth) * imageSize.x,
                    imageMin.y + static_cast<float>(boxY1_ / data.imageHeight) * imageSize.y
                );
                const ImVec2 boxMax(
                    imageMin.x + static_cast<float>(boxX2_ / data.imageWidth) * imageSize.x,
                    imageMin.y + static_cast<float>(boxY2_ / data.imageHeight) * imageSize.y
                );
                drawList->PushClipRect(imageMin, imageMax, true);
                drawList->AddRectFilled(boxMin, boxMax, ImGui::GetColorU32(ImGuiCol_ButtonHovered, 0.25f));
                drawList->AddRect(boxMin, boxMax, ImGui::GetColorU32(ImGuiCol_ButtonHovered), 0.0f, 0, 2.0f);
                drawList->PopClipRect();
            }
        }
        ImGui::EndDisabled();
        ImGui::SetCursorScreenPos(afterFrame);
        if (drawingMode_ && (dragging_ || hasBox_)) {
            ImGui::Text("Source box (xyxy): %.2f, %.2f, %.2f, %.2f px",
                boxX1_, boxY1_, boxX2_, boxY2_);
        }

        if (!drawingMode_ && ImGui::IsMouseHoveringRect(imageMin, imageMax)) {
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

void MaskingContent::UpdateInteraction(const PhaseDisplayData& data) {
    if (promptRunId_ != data.runId || promptSelectionId_ != data.selectionId ||
        !data.maskSelectionEnabled || data.selectionSubmitting) {
        ResetInteraction();
    }
    promptRunId_ = data.runId;
    promptSelectionId_ = data.selectionId;
}

void MaskingContent::ResetInteraction() {
    drawingMode_ = false;
    dragging_ = false;
    hasBox_ = false;
    passedDragThreshold_ = false;
    anchorX_ = anchorY_ = 0.0;
    boxX1_ = boxY1_ = boxX2_ = boxY2_ = 0.0;
}

void MaskingContent::Shutdown() {
    ResetInteraction();
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
