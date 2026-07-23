#include "UIPanel.h"

UIPanel::UIPanel(String name) {
	this->name = name;
	this->type = UIType::UNKNOWN;
	this->activeSelf = true;
}

UIPanel::UIPanel(UIType type, String name) {
	this->type = type;
	this->name = name;
	this->activeSelf = true;
}

UIPanel::UIPanel(UIType type, String name, bool isActive) {
	this->type = type;
	this->name = name;
	this->activeSelf = isActive;
}

String UIPanel::GetName() {
	return this->name;
}

UIType UIPanel::GetType() {
	return this->type;
}

bool UIPanel::IsActive() {
	return this->activeSelf;
}

void UIPanel::SetActive(bool isActive) {
	this->activeSelf = isActive;
}
