#include "MenuToolbar.h"
#include "../UIManager.h"

MenuToolbar::MenuToolbar(String name) : 
	UIPanel(UIType::MENU_TOOLBAR, name) {}

MenuToolbar::~MenuToolbar() {}

void MenuToolbar::Draw() {
	if (ImGui::BeginMainMenuBar()) {
		if (ImGui::BeginMenu("About")) {
			if (ImGui::MenuItem("Credits")) {

			}
			ImGui::EndMenu();
		}

		if (ImGui::BeginMenu("Layout")) {
			if (ImGui::MenuItem("Default Scan")) {
				UIManager::GetInstance()->ApplyLayout(UILayout::DEFAULT);
				//if (dockspace) dockspace->RequestDefaultLayout();
			}

			if (ImGui::MenuItem("Model Viewer")) {
				UIManager::GetInstance()->ApplyLayout(UILayout::MODEL_VIEWER);
			}
			ImGui::EndMenu();
		}

		
	}
	ImGui::EndMainMenuBar();
}

void MenuToolbar::SetDockspace(Dockspace* dockspace) {
	this->dockspace = dockspace;
}