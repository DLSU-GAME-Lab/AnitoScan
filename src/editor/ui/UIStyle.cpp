#include "editor/ui/UIStyle.h"

#include <algorithm>

namespace {
constexpr ImVec4 kAccent(0.20f, 0.48f, 0.82f, 1.0f);
constexpr ImVec4 kAccentHovered(0.25f, 0.56f, 0.94f, 1.0f);
constexpr ImVec4 kAccentActive(0.16f, 0.40f, 0.72f, 1.0f);
constexpr ImVec4 kDanger(0.62f, 0.20f, 0.22f, 1.0f);
constexpr ImVec4 kDangerHovered(0.76f, 0.25f, 0.27f, 1.0f);
constexpr ImVec4 kDangerActive(0.52f, 0.16f, 0.18f, 1.0f);
constexpr ImVec4 kSecondary(0.18f, 0.20f, 0.24f, 1.0f);
constexpr ImVec4 kSecondaryHovered(0.24f, 0.27f, 0.32f, 1.0f);
constexpr ImVec4 kSecondaryActive(0.15f, 0.17f, 0.20f, 1.0f);
constexpr ImVec4 kGhost(0.12f, 0.14f, 0.17f, 1.0f);
constexpr ImVec4 kGhostHovered(0.19f, 0.22f, 0.27f, 1.0f);
constexpr ImVec4 kGhostActive(0.14f, 0.17f, 0.21f, 1.0f);

ImVec4 StatusColor(std::string_view status) {
    if (status == "running") return ImVec4(0.28f, 0.76f, 0.52f, 1.0f);
    if (status == "completed") return ImVec4(0.30f, 0.78f, 0.50f, 1.0f);
    if (status == "pending" || status == "cancelling" || status == "awaiting_export") return ImVec4(0.94f, 0.67f, 0.24f, 1.0f);
    if (status == "failed") return ImVec4(0.94f, 0.36f, 0.38f, 1.0f);
    if (status == "cancelled") return ImVec4(0.76f, 0.40f, 0.42f, 1.0f);
    return ImVec4(0.62f, 0.66f, 0.72f, 1.0f);
}
}

namespace UIStyle {

void ApplyTheme() {
    ImGui::StyleColorsDark();
    ImGuiStyle& style = ImGui::GetStyle();

    style.WindowPadding = ImVec2(16.0f, 14.0f);
    style.FramePadding = ImVec2(10.0f, 6.0f);
    style.CellPadding = ImVec2(8.0f, 6.0f);
    style.ItemSpacing = ImVec2(8.0f, 8.0f);
    style.ItemInnerSpacing = ImVec2(6.0f, 4.0f);
    style.ScrollbarSize = 13.0f;
    style.GrabMinSize = 10.0f;

    style.WindowRounding = 0.0f;
    style.ChildRounding = 3.0f;
    style.FrameRounding = 3.0f;
    style.PopupRounding = 4.0f;
    style.ScrollbarRounding = 4.0f;
    style.GrabRounding = 3.0f;

    style.WindowBorderSize = 0.0f;
    style.ChildBorderSize = 1.0f;
    style.FrameBorderSize = 0.0f;
    style.PopupBorderSize = 1.0f;

    ImVec4* colors = style.Colors;
    colors[ImGuiCol_Text] = ImVec4(0.88f, 0.90f, 0.93f, 1.0f);
    colors[ImGuiCol_TextDisabled] = ImVec4(0.48f, 0.52f, 0.58f, 1.0f);
    colors[ImGuiCol_WindowBg] = ImVec4(0.055f, 0.063f, 0.078f, 1.0f);
    colors[ImGuiCol_ChildBg] = ImVec4(0.075f, 0.086f, 0.105f, 1.0f);
    colors[ImGuiCol_PopupBg] = ImVec4(0.075f, 0.086f, 0.105f, 0.98f);
    colors[ImGuiCol_Border] = ImVec4(0.19f, 0.21f, 0.25f, 1.0f);
    colors[ImGuiCol_Separator] = ImVec4(0.16f, 0.18f, 0.22f, 1.0f);
    colors[ImGuiCol_FrameBg] = ImVec4(0.12f, 0.14f, 0.17f, 1.0f);
    colors[ImGuiCol_FrameBgHovered] = ImVec4(0.16f, 0.19f, 0.23f, 1.0f);
    colors[ImGuiCol_FrameBgActive] = ImVec4(0.19f, 0.23f, 0.28f, 1.0f);
    colors[ImGuiCol_Button] = kSecondary;
    colors[ImGuiCol_ButtonHovered] = kSecondaryHovered;
    colors[ImGuiCol_ButtonActive] = kSecondaryActive;
    colors[ImGuiCol_Header] = ImVec4(0.14f, 0.17f, 0.21f, 1.0f);
    colors[ImGuiCol_HeaderHovered] = ImVec4(0.19f, 0.24f, 0.30f, 1.0f);
    colors[ImGuiCol_HeaderActive] = ImVec4(0.16f, 0.21f, 0.27f, 1.0f);
    colors[ImGuiCol_CheckMark] = kAccent;
    colors[ImGuiCol_SliderGrab] = kAccent;
    colors[ImGuiCol_SliderGrabActive] = kAccentHovered;
    colors[ImGuiCol_TableHeaderBg] = ImVec4(0.10f, 0.12f, 0.15f, 1.0f);
    colors[ImGuiCol_TableRowBg] = ImVec4(0.075f, 0.086f, 0.105f, 1.0f);
    colors[ImGuiCol_TableRowBgAlt] = ImVec4(0.09f, 0.102f, 0.124f, 1.0f);
    colors[ImGuiCol_ScrollbarBg] = ImVec4(0.055f, 0.063f, 0.078f, 1.0f);
    colors[ImGuiCol_ScrollbarGrab] = ImVec4(0.20f, 0.23f, 0.28f, 1.0f);
    colors[ImGuiCol_ScrollbarGrabHovered] = ImVec4(0.27f, 0.31f, 0.37f, 1.0f);
    colors[ImGuiCol_ScrollbarGrabActive] = ImVec4(0.32f, 0.37f, 0.44f, 1.0f);
    colors[ImGuiCol_PlotHistogram] = kAccent;
}

bool Button(const char* label, ButtonKind kind, const ImVec2& size) {
    ImVec4 normal;
    ImVec4 hovered;
    ImVec4 active;
    switch (kind) {
    case ButtonKind::Primary:
        normal = kAccent;
        hovered = kAccentHovered;
        active = kAccentActive;
        break;
    case ButtonKind::Danger:
        normal = kDanger;
        hovered = kDangerHovered;
        active = kDangerActive;
        break;
    case ButtonKind::Ghost:
        normal = kGhost;
        hovered = kGhostHovered;
        active = kGhostActive;
        break;
    case ButtonKind::Secondary:
        normal = kSecondary;
        hovered = kSecondaryHovered;
        active = kSecondaryActive;
        break;
    }

    ImGui::PushStyleColor(ImGuiCol_Button, normal);
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, hovered);
    ImGui::PushStyleColor(ImGuiCol_ButtonActive, active);
    const bool clicked = ImGui::Button(label, size);
    ImGui::PopStyleColor(3);
    return clicked;
}

void StatusBadge(std::string_view status) {
    const ImVec4 color = StatusColor(status);
    if (status == "awaiting_export") status = "Awaiting export";
    const ImVec2 textSize = ImGui::CalcTextSize(status.data(), status.data() + status.size());
    const ImVec2 padding(7.0f, 3.0f);
    const ImVec2 position = ImGui::GetCursorScreenPos();
    const ImVec2 size(textSize.x + padding.x * 2.0f, textSize.y + padding.y * 2.0f);
    ImDrawList* drawList = ImGui::GetWindowDrawList();
    drawList->AddRectFilled(
        position,
        ImVec2(position.x + size.x, position.y + size.y),
        ImGui::GetColorU32(ImVec4(color.x, color.y, color.z, 0.16f)),
        3.0f
    );
    drawList->AddRect(
        position,
        ImVec2(position.x + size.x, position.y + size.y),
        ImGui::GetColorU32(ImVec4(color.x, color.y, color.z, 0.42f)),
        3.0f
    );
    drawList->AddText(
        ImVec2(position.x + padding.x, position.y + padding.y),
        ImGui::GetColorU32(color),
        status.data(),
        status.data() + status.size()
    );
    ImGui::Dummy(size);
}

void SectionTitle(const char* title, const char* description) {
    ImGui::TextDisabled("%s", title);
    if (description && description[0] != '\0') {
        ImGui::TextWrapped("%s", description);
    }
    ImGui::Spacing();
}

void CenteredMessage(const char* title, const char* description) {
    const ImVec2 available = ImGui::GetContentRegionAvail();
    const ImVec2 titleSize = ImGui::CalcTextSize(title);
    const ImVec2 descriptionSize = description ? ImGui::CalcTextSize(description) : ImVec2(0.0f, 0.0f);
    const float spacing = description ? ImGui::GetStyle().ItemSpacing.y : 0.0f;
    const float totalHeight = titleSize.y + spacing + descriptionSize.y;
    const ImVec2 start = ImGui::GetCursorPos();
    ImGui::SetCursorPosY(start.y + std::max(0.0f, (available.y - totalHeight) * 0.5f));
    ImGui::SetCursorPosX(start.x + std::max(0.0f, (available.x - titleSize.x) * 0.5f));
    ImGui::TextUnformatted(title);
    if (description) {
        ImGui::SetCursorPosX(start.x + std::max(0.0f, (available.x - descriptionSize.x) * 0.5f));
        ImGui::TextDisabled("%s", description);
    }
}

} // namespace UIStyle
