#pragma once

#include "editor/ui/components/Viewport.h"

#include <vector>

struct PostExportData;
struct UIInput;

class PostExportScreen {
public:
    void Render(const PostExportData& data, std::vector<UIInput>& inputs);

    int GetViewportWidth() const;
    int GetViewportHeight() const;
    bool IsViewportHovered() const;
    bool ConsumeRecenterRequest();

private:
    Viewport viewport_;
    bool recenterRequested_ = false;
};
