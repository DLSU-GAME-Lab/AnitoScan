#include "editor/ui/components/LogView.h"

#include "editor/ui/UIStyle.h"

#include <algorithm>

#include <imgui.h>

void LogView::Render(const std::vector<std::string>& logs) {
    ImGui::Separator();

    constexpr float footerHeight = 30.0f;
    const ImVec2 footerCursor = ImGui::GetCursorPos();
    const ImVec2 footerPosition = ImGui::GetCursorScreenPos();
    const ImVec2 footerSize(
        std::max(0.0f, ImGui::GetContentRegionAvail().x),
        footerHeight
    );
    ImDrawList* drawList = ImGui::GetWindowDrawList();
    drawList->AddRectFilled(
        footerPosition,
        ImVec2(footerPosition.x + footerSize.x, footerPosition.y + footerSize.y),
        ImGui::GetColorU32(ImVec4(0.075f, 0.086f, 0.105f, 1.0f)),
        3.0f
    );
    drawList->AddRect(
        footerPosition,
        ImVec2(footerPosition.x + footerSize.x, footerPosition.y + footerSize.y),
        ImGui::GetColorU32(ImGuiCol_Border),
        3.0f
    );

    const float textY = footerPosition.y +
        (footerHeight - ImGui::GetTextLineHeight()) * 0.5f;
    ImGui::SetCursorScreenPos(ImVec2(footerPosition.x + 10.0f, textY));
    ImGui::TextDisabled("CONSOLE");
    ImGui::SameLine(0.0f, 8.0f);
    ImGui::TextDisabled("%zu entries", logs.size());

    const char* toggleLabel = expanded_ ? "Hide##LogToggle" : "Show##LogToggle";
    const ImVec2 toggleTextSize = ImGui::CalcTextSize(toggleLabel);
    const ImVec2 toggleSize(toggleTextSize.x + 16.0f, toggleTextSize.y + 6.0f);
    ImGui::SetCursorScreenPos(ImVec2(
        footerPosition.x + std::max(0.0f, footerSize.x - toggleSize.x - 5.0f),
        footerPosition.y + (footerHeight - toggleSize.y) * 0.5f
    ));
    ImGui::PushStyleVar(ImGuiStyleVar_FramePadding, ImVec2(8.0f, 3.0f));
    if (UIStyle::Button(toggleLabel, UIStyle::ButtonKind::Ghost, toggleSize)) {
        expanded_ = !expanded_;
    }
    ImGui::PopStyleVar();
    ImGui::SetCursorPos(ImVec2(footerCursor.x, footerCursor.y + footerHeight));
    ImGui::Dummy(ImVec2(0.0f, 0.0f));

    if (!expanded_) {
        return;
    }

    ImGui::Spacing();
    ImGui::PushStyleColor(ImGuiCol_ChildBg, ImVec4(0.035f, 0.041f, 0.052f, 1.0f));
    ImGui::PushStyleColor(ImGuiCol_Border, ImVec4(0.16f, 0.18f, 0.22f, 1.0f));
    ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(0.78f, 0.82f, 0.87f, 1.0f));
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(10.0f, 8.0f));
    if (ImGui::BeginChild(
        "Logs",
        ImVec2(0.0f, 150.0f),
        ImGuiChildFlags_Borders | ImGuiChildFlags_AlwaysUseWindowPadding
    )) {
        for (const std::string& log : logs) {
            ImGui::TextUnformatted(log.c_str());
        }
    }
    ImGui::EndChild();
    ImGui::PopStyleVar();
    ImGui::PopStyleColor(3);
}

float LogView::GetPreferredHeight() const {
    return expanded_ ? 190.0f : 34.0f;
}
