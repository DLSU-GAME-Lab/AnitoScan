#include "App.h"

int main(int, char**) {
    App app;
    if (!app.Initialize()) {
        return 1;
    }

    app.Run();
    return 0;
}
