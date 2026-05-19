#include "UIPanel.h"

UIPanel::UIPanel(UIType type) {
	this->type = type;
	this->activeSelf = true;
}

UIPanel::UIPanel(UIType type, bool isActive) {
	this->type = type;
	this->activeSelf = isActive;
}

UIPanel::~UIPanel() {}

UIType UIPanel::GetType() {
	return this->type;
}

bool UIPanel::IsActive() {
	return this->activeSelf;
}

void UIPanel::SetActive(bool isActive) {
	this->activeSelf = isActive;
}