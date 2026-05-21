#pragma once
#include "../UIPanel.h"

class DockSpace : public UIPanel {
public:
	DockSpace();
	~DockSpace();
private:
	void Draw() override;
};