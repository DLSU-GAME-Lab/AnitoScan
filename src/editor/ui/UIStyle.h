#pragma once

#include <string_view>

#include <imgui.h>

namespace UIStyle {

enum class ButtonKind {
    Primary,
    Secondary,
    Danger,
    Ghost
};

void ApplyTheme();

bool Button(
    const char* label,
    ButtonKind kind = ButtonKind::Secondary,
    const ImVec2& size = ImVec2(0.0f, 0.0f)
);

void StatusBadge(std::string_view status);
void SectionTitle(const char* title, const char* description = nullptr);
void CenteredMessage(const char* title, const char* description = nullptr);

} // namespace UIStyle
