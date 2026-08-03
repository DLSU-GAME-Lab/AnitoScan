#pragma once

class Viewport {
public:
    void Render(unsigned int textureId);

    int GetWidth() const;
    int GetHeight() const;

private:
    int width_ = 0;
    int height_ = 0;
};
