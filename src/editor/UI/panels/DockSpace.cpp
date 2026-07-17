#include "Dockspace.h"

Dockspace::Dockspace(String name)
	: UIPanel(UIType::DOCKSPACE, name) {}

Dockspace::~Dockspace() {}


// Configures and renders the primary application docking surface
void Dockspace::Draw() {
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

	this->dockspaceID = ImGui::GetID("MainDockspace");

	static bool layoutInitialized = false;
	if (!layoutInitialized) {
		layoutInitialized = true;
		if (ImGui::DockBuilderGetNode(this->dockspaceID) == nullptr) {
			SetupDefaultLayout();
		}
	}

	if (this->pendingLayout == PendingLayout::Default) {
		SetupDefaultLayout();
		this->pendingLayout = PendingLayout::None;
	}
	else if (this->pendingLayout == PendingLayout::ModelViewer) {
		SetupModelViewerLayout();
		this->pendingLayout = PendingLayout::ModelViewer;
	}

	//SetupDefaultLayout(dockspaceID);
	ImGui::DockSpace(this->dockspaceID, ImVec2(0 , 0), ImGuiDockNodeFlags_PassthruCentralNode);
	ImGui::End();
}

void Dockspace::SetupDefaultLayout() {
	this->dockspaceID = ImGui::GetID("MainDockspace");

	ImGui::DockBuilderRemoveNode(this->dockspaceID);
	ImGui::DockBuilderAddNode(this->dockspaceID, ImGuiDockNodeFlags_PassthruCentralNode);
	ImGui::DockBuilderSetNodeSize(this->dockspaceID, ImGui::GetMainViewport()->WorkSize);

	//File viewer section
	ImGuiID dockMain = this->dockspaceID;
	ImGuiID dockRight = ImGui::DockBuilderSplitNode(dockMain, ImGuiDir_Right, 0.22f, nullptr, &dockMain);
	
	//remaining left area: top(viewer) bottom(overview/log)
	ImGuiID dockBottom = ImGui::DockBuilderSplitNode(dockMain, ImGuiDir_Down, 0.38f, nullptr, &dockMain);

	//split bottom strip
	ImGuiID dockBottomLeft = ImGui::DockBuilderSplitNode(dockBottom, ImGuiDir_Left, 0.44f, nullptr, &dockBottom);


	ImGuiDockNode* viewportNode = ImGui::DockBuilderGetNode(dockMain);
	if (viewportNode)
		viewportNode->LocalFlags |= ImGuiDockNodeFlags_AutoHideTabBar;

	ImGui::DockBuilderDockWindow("Viewport", dockMain);
	ImGui::DockBuilderDockWindow("Overview", dockBottomLeft);
	ImGui::DockBuilderDockWindow("Log", dockBottom);

	ImGui::DockBuilderDockWindow("Capture", dockRight);
	ImGui::DockBuilderDockWindow("Masking", dockRight);

	ImGui::DockBuilderFinish(this->dockspaceID);
}


void Dockspace::SetupModelViewerLayout() {
	this->dockspaceID = ImGui::GetID("MainDockspace");

	ImGui::DockBuilderRemoveNode(this->dockspaceID);
	ImGui::DockBuilderAddNode(this->dockspaceID, ImGuiDockNodeFlags_PassthruCentralNode);
	ImGui::DockBuilderSetNodeSize(this->dockspaceID, ImGui::GetMainViewport()->WorkSize);

	//ImGuiID dockMain = this->dockspaceID;
	//ImGuiDockNode* viewportNode = ImGui::DockBuilderGetNode(dockMain);
	//if (viewportNode)
	//	viewportNode->LocalFlags |= ImGuiDockNodeFlags_AutoHideTabBar;

	ImGui::DockBuilderDockWindow("Viewport", this->dockspaceID);

	ImGui::DockBuilderFinish(this->dockspaceID);
}

void Dockspace::RequestDefaultLayout() {
	this->pendingLayout = PendingLayout::Default;
}

void Dockspace::RequestModelViewerLayout() {
	this->pendingLayout = PendingLayout::ModelViewer;
}