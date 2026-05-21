#include "App.h"

int main(int argc, char** args) {
	App app(1400, 800);

	app.Initialize();
	app.Run();

	return 0;
}
