#include "editor/ui/components/ExportContent.h"

#include "editor/ui/UIManager.h"
#include "editor/ui/UIStyle.h"

#include <imgui.h>

#include <algorithm>
#include <cstdio>
#include <filesystem>
#include <string>

void ExportContent::Render(const PhaseDisplayData& data, std::vector<UIInput>& inputs) {
    if (!exportSettingsInitialized_ || exportRunId_ != data.runId) {
        exportSettingsInitialized_ = true;
        exportRunId_ = data.runId;
        exportFormat_ = "obj";
        autoAssetName_.clear();
        destination_.fill('\0');
        assetName_.fill('\0');
        destinationInitialized_ = false;
    }

    const std::filesystem::path source(data.selectedOutputModelPath);
    if (!destinationInitialized_ && !source.empty()) {
        const std::string destination = (source.parent_path().parent_path() / "exports").string();
        std::snprintf(destination_.data(), destination_.size(), "%s", destination.c_str());
        destinationInitialized_ = true;
    }
    const auto updateAutoAssetName = [&]() {
        const std::string nextName = source.empty()
            ? std::string{} : source.stem().string();
        if (std::string(assetName_.data()) == autoAssetName_) {
            std::snprintf(assetName_.data(), assetName_.size(), "%s", nextName.c_str());
        }
        autoAssetName_ = nextName;
    };
    updateAutoAssetName();
    const bool busy = data.exportState.busy;
    const auto supportsFormat = [&](const char* format) {
        return std::find(data.exportFormats.begin(), data.exportFormats.end(), format)
            != data.exportFormats.end();
    };

    ImGui::TextUnformatted("Export asset");
    ImGui::TextWrapped("Current prepared output: %s", source.empty() ? "None" : data.selectedOutputModelPath.c_str());
    ImGui::TextWrapped("Export the current prepared output successfully to continue to preview. The prepared OBJ is retained.");

    ImGui::BeginDisabled(busy);
    ImGui::BeginDisabled(!supportsFormat("obj"));
    if (ImGui::RadioButton("OBJ", exportFormat_ == "obj")) {
        exportFormat_ = "obj";
        updateAutoAssetName();
    }
    ImGui::EndDisabled();
    ImGui::SameLine();
    ImGui::BeginDisabled(!supportsFormat("glb"));
    if (ImGui::RadioButton("GLB", exportFormat_ == "glb")) {
        exportFormat_ = "glb";
        updateAutoAssetName();
    }
    ImGui::EndDisabled();
    if (!supportsFormat("glb")) {
        ImGui::TextWrapped("GLB requires trimesh.");
    }
    ImGui::TextUnformatted("Destination folder (absolute path)");
    ImGui::SetNextItemWidth(-1.0f);
    ImGui::InputText("##ExportDestination", destination_.data(), destination_.size());
    ImGui::TextUnformatted("Asset name");
    ImGui::SetNextItemWidth(-1.0f);
    ImGui::InputText("##ExportAssetName", assetName_.data(), assetName_.size());
    ImGui::EndDisabled();

    const std::string destination(destination_.data());
    const std::string assetName(assetName_.data());
    const std::filesystem::path destinationPath(destination);
    const bool absoluteDestination = destinationPath.is_absolute();
    const bool validName = !assetName.empty() && assetName != "." && assetName != ".."
        && assetName.find_first_of("/\\\r\n") == std::string::npos;
    const bool validDestination = !destination.empty() && absoluteDestination
        && destination.find_first_of("\r\n") == std::string::npos;
    ImGui::TextWrapped("Use an absolute destination path; destination parents are auto-created. "
                       "Export creates a dedicated destination/asset_name folder and never overwrites "
                       "an existing output folder. OBJ keeps the original filenames.");
    if (!destination.empty() && !absoluteDestination) {
        ImGui::TextWrapped("Destination must be an absolute folder path.");
    }
    if (!assetName.empty() && !validName) {
        ImGui::TextWrapped("Asset name must be a single folder name, not a path, '.' or '..'.");
    }
    if (validDestination && validName) {
        const std::string target = (destinationPath / assetName).string();
        ImGui::TextWrapped("Output folder: %s", target.c_str());
    }
    if (!data.exportAvailable) {
        ImGui::TextWrapped("Export is unavailable for the current source.");
    }
    ImGui::BeginDisabled(busy || !data.exportAvailable || source.empty()
        || !supportsFormat(exportFormat_.c_str()) || !validDestination || !validName);
    if (UIStyle::Button("Export", UIStyle::ButtonKind::Primary)) {
        inputs.push_back({UIClick::ExportAsset, exportFormat_ + "\n" + destination + "\n" + assetName});
    }
    ImGui::EndDisabled();
    if (busy) {
        ImGui::TextWrapped("Exporting... Navigation is disabled until export finishes.");
    }
    if (!data.exportState.error.empty()) {
        ImGui::TextWrapped("Export error: %s", data.exportState.error.c_str());
    } else if (!busy && !data.exportState.outputPath.empty()) {
        ImGui::TextWrapped("Export complete: %s", data.exportState.outputPath.c_str());
    }

}
