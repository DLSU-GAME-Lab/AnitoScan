#include "DockSpace.h"

DockSpace::DockSpace(String name) 
	: UIPanel(UIType::DOCKSPACE, name) {}

DockSpace::~DockSpace() {}

// Configures and renders the primary application docking surface
void DockSpace::Draw() {
	ImGuiViewport* viewport = ImGui::GetMainViewport();
	ImGui::SetNextWindowPos(viewport->WorkPos);
	ImGui::SetNextWindowSize(viewport->WorkSize);
	ImGui::SetNextWindowViewport(viewport->ID);

	ImGuiWindowFlags flags =
		ImGuiWindowFlags_NoTitleBar |
		ImGuiWindowFlags_NoCollapse | 
		ImGuiWindowFlags_NoMove		|
		ImGuiWindowFlags_NoResize	|
		ImGuiWindowFlags_NoBringToFrontOnFocus |
		ImGuiWindowFlags_NoNavFocus	|
		ImGuiWindowFlags_NoBackground |
		ImGuiWindowFlags_NoDocking;
	
	ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(0, 0));
	ImGui::Begin("##dockspace", nullptr, flags);
	ImGui::PopStyleVar();

	ImGuiID dockspaceID = ImGui::GetID("MainDockSpace");
	ImGui::DockSpace(dockspaceID, ImVec2(0 , 0), ImGuiDockNodeFlags_PassthruCentralNode);

	static bool layoutInitialized = false;
	if (!layoutInitialized) {
		layoutInitialized = true;
	}

	//SetupDefaultLayout(dockspaceID);
	ImGui::End();
}

//void DockSpace::SetupDefaultLayout(ImGuiID dockspaceID) {
//	ImGui::DockBuilderRemoveNode(dockspaceID);
//	ImGui::DockBuilderAddNode(dockspaceID, ImGuiDockNodeFlags_PassthruCentralNode);
//	ImGui::DockBuilderSetNodeSize(dockspaceID, ImGui::GetMainViewport()->WorkSize);
//
//	//ImGuiID leftID, remainderID;
//	//ImGui::DockBuilderSplitNode(dockspaceID, ImGuiDir_Left, 0.25f, &leftID, &remainderID);
//
//	//ImGuiID centerID, bottomID;
//	//ImGui::DockBuilderSplitNode(remainderID, ImGuiDir_Down, 0.25f, &bottomID, &centerID);
//	//ImGuiID centerLeftID, centerRightID;
//	//ImGui::DockBuilderSplitNode(centerID, ImGuiDir_Left, 0.5f, &centerLeftID, &centerRightID);
//
//
//	ImGuiID leftID, rightID;
//	ImGui::DockBuilderSplitNode(dockspaceID, ImGuiDir_Left, 0.5f, &leftID, &rightID);
//
//	ImGui::DockBuilderDockWindow("Scan Panel", leftID);
//	ImGui::DockBuilderDockWindow("Capture", rightID);
//	//ImGui::DockBuilderDockWindow("Phase 2", centerRightID);
//	//ImGui::DockBuilderDockWindow("Log", bottomID);
//
//	ImGui::DockBuilderFinish(dockspaceID);
//}