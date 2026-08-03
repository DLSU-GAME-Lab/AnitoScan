#include "editor/ui/UIManager.h"

void UIManager::Render(unsigned int textureId) {
    postExportScreen_.Render(textureId);
}

int UIManager::GetViewportWidth() const {
    return postExportScreen_.GetViewportWidth();
}

int UIManager::GetViewportHeight() const {
    return postExportScreen_.GetViewportHeight();
}
