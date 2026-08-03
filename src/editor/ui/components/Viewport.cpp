#include "editor/ui/components/Viewport.h"

#include <imgui.h>

#include <algorithm>

void Viewport::Render(unsigned int textureId) {
    ImGui::BeginChild("Viewport", ImVec2(0.0f, 0.0f), true);

    const ImVec2 availableSpace = ImGui::GetContentRegionAvail();
    width_ = std::max(0, static_cast<int>(availableSpace.x));
    height_ = std::max(0, static_cast<int>(availableSpace.y));

    if (textureId != 0 && width_ > 0 && height_ > 0) {
        ImGui::Image(
            static_cast<ImTextureID>(textureId),
            ImVec2(static_cast<float>(width_), static_cast<float>(height_)),
            ImVec2(0.0f, 1.0f),
            ImVec2(1.0f, 0.0f)
        );
    } else {
        constexpr const char* message = "No completed model available";
        const ImVec2 textSize = ImGui::CalcTextSize(message);
        const ImVec2 cursorPosition = ImGui::GetCursorPos();

        ImGui::SetCursorPos(ImVec2(
            cursorPosition.x + (availableSpace.x - textSize.x) * 0.5f,
            cursorPosition.y + (availableSpace.y - textSize.y) * 0.5f
        ));
        ImGui::TextUnformatted(message);
    }

    ImGui::EndChild();
}

int Viewport::GetWidth() const {
    return width_;
}

int Viewport::GetHeight() const {
    return height_;
}
