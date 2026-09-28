#pragma once

#include <string>
#include <vector>

class LogView {
public:
    void Render(const std::vector<std::string>& logs);
    float GetPreferredHeight() const;

private:
    bool expanded_ = false;
};
