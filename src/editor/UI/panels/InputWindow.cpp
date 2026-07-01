#include "InputWindow.h"
#include "OverviewPanel.h"


// Initializes active state and Sets the target directory of the ImGui file browser
// Filters access to .mp4 and .MOV files only
InputWindow::InputWindow(String name) : UIPanel(UIType::INPUT, name, false) {
    this->show = this->activeSelf;
    this->fileDialog.SetTypeFilters({ ".mp4", ".MOV" });
    this->fileDialog.SetPwd(std::filesystem::current_path() / "data" / "input");
    
    InitializeDropDown();
}

InputWindow::~InputWindow() {}

// Renders the input window and binds the necessary input values (input file, folder name, minimum frames, quality)
// before sending it over to the overview panel
void InputWindow::Draw() {
    if (this->show) {
        ImGui::OpenPopup(this->GetName().c_str());        
    }

    ImVec2 center = ImGui::GetMainViewport()->GetCenter();
    ImGui::SetNextWindowPos(center, ImGuiCond_Always, ImVec2(0.5f, 0.5f));
    ImGui::SetNextWindowSize(ImVec2(700, 500), ImGuiCond_Always);

    ImGuiWindowFlags flags = ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoResize;
    if (ImGui::BeginPopupModal(this->GetName().c_str(), &this->show, flags)) {
       
        //INPUT VIDEO SELECTION
        ImGui::SeparatorText("Select Input Video");
        ImGui::Text("File name: ");
        if (!this->hasInputVideo) {
            if (ImGui::Button("Open File Browser")) {
                fileDialog.Open();
            }
        }
        else {
            ImGui::SameLine();
            HighlightImGuiText(inputFile, UIColor::YELLOW);
            ImGui::SameLine();
            RightAlignElement("Change##1");
            if (ImGui::Button("Change##1")) {
                hasInputVideo = false;
                fileDialog.ClearSelected();
                fileDialog.Open();
            }
        }

        fileDialog.Display();

        if (fileDialog.HasSelected()) {
            hasInputVideo = true;
            std::filesystem::path path = fileDialog.GetSelected();
            inputFile = path.filename().string();
        }
        ImGui::NewLine();


        //NAME
        ImGui::BeginDisabled(!this->hasInputVideo);
        ImGui::SeparatorText("Enter the name of the output folder");
        ImGui::Text("Name: ");

        if (!hasName) {
            bool confirm = ImGui::InputText("##FolderName", this->inputText, sizeof(this->inputText), ImGuiInputTextFlags_EnterReturnsTrue);
            ImGui::SameLine();
            confirm |= ImGui::Button("Enter"); //either Enter key or button click

            String errorMsg;
            bool validName = ValidateFolderName(this->inputText, errorMsg);
            if (!validName && this->inputText[0] != '\0') {
                HighlightImGuiText(errorMsg, UIColor::RED);
            }

            if (confirm && validName) {
                this->folderName = String(this->inputText);
                this->hasName = true;
                this->hasCompleteInput = true;
            }
        }
        else {
            ImGui::SameLine();
            HighlightImGuiText(this->folderName, UIColor::YELLOW);
            ImGui::SameLine();
            RightAlignElement("Change##2");
            if (ImGui::Button("Change##2")) {
                this->hasName = false;
            }
        }
        ImGui::EndDisabled();
        ImGui::NewLine();

        //MINIMUM FRAMES
        ImGui::BeginDisabled(!this->hasName);
        static int indexFrames = 0;
        
        ImGui::SeparatorText("Select the number of Minimum Frames");
        ImGui::Combo("Minimum Frames", &indexFrames, this->items.data(), this->items.size());
        ImGui::EndDisabled();
        ImGui::NewLine();

        //QUALITY
        ImGui::BeginDisabled(!this->hasName);
        ImGui::SeparatorText("Select the quality of the model to be exported");
        const char* options[] = { "fast", "medium", "detailed" };

        static int indexQuality = 0;
        ImGui::Combo("Export Quality", &indexQuality, options, IM_ARRAYSIZE(options));

        ImGui::EndDisabled();
        ImGui::NewLine();


        ImGui::BeginDisabled(!this->hasCompleteInput);
        if (ImGui::Button("Done")) {
            OverviewPanel* overview = static_cast<OverviewPanel*>(UIManager::GetInstance()->GetPanelByType(UIType::OVERVIEW));
            if (overview) {
                overview->SetInput(
                    this->inputFile,
                    this->folderName,
                    std::stoi(this->items[indexFrames]),
                    options[indexQuality]);
            }
            this->activeSelf = false;
            ImGui::CloseCurrentPopup();
        }
        ImGui::EndDisabled();
        ImGui::EndPopup();
        
    }
};
    

// Activates the window visibility flags
void InputWindow::ShowWindow() {
    this->activeSelf = true;
    this->show = true;
}


// Generates dynamic numerical values for the frame selection dropdown list 
void InputWindow::InitializeDropDown() {
    //for (const char* ptr : this->items) {
    //    free((void*)ptr);
    //}
    //this->items.clear();

    int gap = 10;
    std::vector<String> tempItems;

    int min = this->minOption;
    while (min <= this->maxOption) {
        String temp = std::to_string(min);
        this->items.push_back(_strdup(temp.c_str()));
        min += gap;
    }
}

// Helper function for validating the input for the output folder name
bool InputWindow::ValidateFolderName(String name, String& outErrorMsg) {
    if (name.empty() || name[0] == '\0') {
        outErrorMsg = "Folder name cannot be empty.";
        return false;
    }

    const char* checkFor[] = { "<", ">", ":", "/", "\\", "|", "?", "*" };
    for (const char* c : checkFor) {
        if (name.find(c) != std::string::npos) {
            outErrorMsg = "Must not contain '" + String(c) + "' character.";
            return false;
        }
    }

    return true;
}