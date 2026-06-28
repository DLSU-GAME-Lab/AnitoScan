#include "App.h"

int main(int argc, char** args) {
	App app(1920, 1000);
	app.Initialize();
	app.Run();

	return 0;
}
