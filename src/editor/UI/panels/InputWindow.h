#pragma once

#include "../UIPanel.h"
#include <vector>
#include <iterator>

class OverviewPanel;
class InputWindow : public UIPanel {
public:
	InputWindow(String name);
	~InputWindow();

	void Draw() override;
	void ShowWindow();

private:
	void InitializeDropDown();
	bool ValidateFolderName(String name, String& outErrorMsg);
//	void MakeNewRun();
//	void SelectPreviousRun();

private:

	bool show;
	bool hasInputVideo = false;
	bool hasName = false;
	bool hasCompleteInput = false;
	bool validInput = false;
	bool selectPrevRun = false;

	ImGui::FileBrowser fileDialog;
	char inputText[256] = "";
	String folderName;
	String inputFile;

	const int minOption = 60;
	const int maxOption = 300;
	std::vector<const char*> items;
};