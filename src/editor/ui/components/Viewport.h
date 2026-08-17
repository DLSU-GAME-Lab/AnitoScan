#pragma once

class Viewport {
public:
    void Render(unsigned int textureId);

    int GetWidth() const;
    int GetHeight() const;
    bool IsHovered() const;

private:
    int width_ = 0;
    int height_ = 0;
    bool hovered_ = false;
};
