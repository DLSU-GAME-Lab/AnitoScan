#include "editor/ui/components/Viewport.h"

#include "editor/ui/UIStyle.h"

#include <imgui.h>

#include <algorithm>

void Viewport::Render(unsigned int textureId) {
    ImGui::PushStyleColor(ImGuiCol_ChildBg, ImVec4(0.035f, 0.041f, 0.052f, 1.0f));
    ImGui::PushStyleColor(ImGuiCol_Border, ImVec4(0.18f, 0.20f, 0.24f, 1.0f));
    ImGui::PushStyleVar(ImGuiStyleVar_ChildRounding, 3.0f);
    ImGui::BeginChild("Viewport", ImVec2(0.0f, 0.0f), true);
    ImGui::PopStyleVar();
    ImGui::PopStyleColor(2);

    const ImVec2 panelOrigin = ImGui::GetCursorScreenPos();
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
        ImGui::PushStyleColor(
            ImGuiCol_Text,
            ImGui::GetStyleColorVec4(ImGuiCol_TextDisabled)
        );
        UIStyle::CenteredMessage(
            "No completed model available",
            "Complete a run to load the 3D preview."
        );
        ImGui::PopStyleColor();
    }

    constexpr const char* overlayLabel = "3D PREVIEW";
    const ImVec2 overlayTextSize = ImGui::CalcTextSize(overlayLabel);
    const ImVec2 overlayMin(panelOrigin.x + 10.0f, panelOrigin.y + 10.0f);
    const ImVec2 overlayMax(
        overlayMin.x + overlayTextSize.x + 14.0f,
        overlayMin.y + overlayTextSize.y + 8.0f
    );
    ImDrawList* drawList = ImGui::GetWindowDrawList();
    drawList->AddRectFilled(
        overlayMin,
        overlayMax,
        ImGui::GetColorU32(ImVec4(0.035f, 0.041f, 0.052f, 0.88f)),
        3.0f
    );
    drawList->AddRect(
        overlayMin,
        overlayMax,
        ImGui::GetColorU32(ImVec4(0.24f, 0.27f, 0.32f, 0.90f)),
        3.0f
    );
    drawList->AddText(
        ImVec2(overlayMin.x + 7.0f, overlayMin.y + 4.0f),
        ImGui::GetColorU32(ImGuiCol_TextDisabled),
        overlayLabel
    );

    hovered_ = ImGui::IsWindowHovered();
    ImGui::EndChild();
}

int Viewport::GetWidth() const {
    return width_;
}

int Viewport::GetHeight() const {
    return height_;
}

bool Viewport::IsHovered() const {
    return hovered_;
}
