#include "MenuToolbar.h"
#include "../UIManager.h"

MenuToolbar::MenuToolbar(String name) : 
	UIPanel(UIType::MENU_TOOLBAR, name) {

	this->fileDialog.SetTypeFilters({ ".OBJ" });
	std::filesystem::path rootPath(PROJECT_ROOT_DIR);
	this->fileDialog.SetPwd(rootPath / "data" / "output");
}

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
				}

				if (ImGui::MenuItem("Model Viewer")) {
					UIManager::GetInstance()->ApplyLayout(UILayout::MODEL_VIEWER);
				}
				ImGui::EndMenu();
			}

			if (ImGui::BeginMenu("Import")) {
				if (ImGui::MenuItem("3D Model")) {
					this->displayImport = true;	
					fileDialog.Open();		
				}
				ImGui::EndMenu();
			}

		
			ImGui::EndMainMenuBar();
		}

		if (this->displayImport) {
			SelectModelToImport();
		}
	}

	void MenuToolbar::SetDockspace(Dockspace* dockspace) {
		this->dockspace = dockspace;
	}


	void MenuToolbar::SelectModelToImport() {
		fileDialog.Display();

		if (fileDialog.HasSelected()) {
			std::filesystem::path filePath = fileDialog.GetSelected();

			ViewportPanel* panel = static_cast<ViewportPanel*>(UIManager::GetInstance()->GetPanelByType(UIType::VIEWPORT));
			panel->LoadOutputModel(filePath);
			this->displayImport = false;
		}
	}
