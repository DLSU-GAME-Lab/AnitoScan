#include "../IPCClient.h"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <thread>
#include <vector>

namespace {

std::string ReadPythonVersion(const std::filesystem::path& projectRoot) {
	std::ifstream input(projectRoot / ".python-version");
	if (!input) return {};

	std::string version(
		(std::istreambuf_iterator<char>(input)),
		std::istreambuf_iterator<char>());
	version.erase(
		std::remove_if(version.begin(), version.end(), [](unsigned char character) {
			return std::isspace(character) != 0;
		}),
		version.end());
	return version;
}

bool WaitForMessage(
	IPCClient& client,
	std::string_view expectedType,
	BackendMessage& result,
	std::chrono::seconds timeout) {
	const auto deadline = std::chrono::steady_clock::now() + timeout;
	while (std::chrono::steady_clock::now() < deadline) {
		std::vector<BackendMessage> messages;
		client.Poll(messages);
		for (BackendMessage& message : messages) {
			if (message.type == expectedType) {
				result = std::move(message);
				return true;
			}
			std::cerr << "Unexpected stdout message: " << message.raw << std::endl;
			return false;
		}
		std::this_thread::sleep_for(std::chrono::milliseconds(20));
	}
	return false;
}

} // namespace

int main() {
	const std::filesystem::path projectRoot(PROJECT_ROOT_DIR);
	const std::string pythonVersion = ReadPythonVersion(projectRoot);
	if (pythonVersion.empty()) {
		std::cerr << "Unable to read .python-version" << std::endl;
		return 1;
	}

	const std::string childProgram =
		"import json,sys,time; "
		"print('smoke diagnostic', file=sys.stderr, flush=True); "
		"print(json.dumps({'type':'smoke_ready'}), flush=True); "
		"message=json.loads(sys.stdin.readline()); "
		"print(json.dumps({'type':'smoke_echo','value':message.get('value')}), flush=True); "
		"time.sleep(60)";

	IPCClient client;
	const std::vector<std::string> arguments{
		"run",
		"--isolated",
		"--no-project",
		"--python",
		pythonVersion,
		"--",
		"python",
		"-u",
		"-c",
		childProgram,
	};
	if (!client.Start(UV_EXECUTABLE_PATH, arguments)) {
		std::cerr << "Failed to launch isolated uv smoke process" << std::endl;
		return 1;
	}

	BackendMessage ready;
	if (!WaitForMessage(client, "smoke_ready", ready, std::chrono::seconds(60))) {
		std::cerr << "Did not receive smoke_ready" << std::endl;
		client.Shutdown();
		return 1;
	}

	if (!client.Send(R"({"type":"smoke_ping","value":42})")) {
		client.Shutdown();
		return 1;
	}

	BackendMessage echo;
	if (!WaitForMessage(client, "smoke_echo", echo, std::chrono::seconds(10))) {
		std::cerr << "Did not receive smoke_echo" << std::endl;
		client.Shutdown();
		return 1;
	}
	if (echo.raw.find("42") == std::string::npos) {
		std::cerr << "Smoke response did not preserve the payload: " << echo.raw << std::endl;
		client.Shutdown();
		return 1;
	}

	if (!client.Restart()) {
		std::cerr << "Failed to restart configured smoke process" << std::endl;
		return 1;
	}

	if (!WaitForMessage(client, "smoke_ready", ready, std::chrono::seconds(60))) {
		std::cerr << "Did not receive smoke_ready after restart" << std::endl;
		client.Shutdown();
		return 1;
	}
	if (!client.Send(R"({"type":"smoke_ping","value":84})")) {
		client.Shutdown();
		return 1;
	}
	if (!WaitForMessage(client, "smoke_echo", echo, std::chrono::seconds(10)) ||
		echo.raw.find("84") == std::string::npos) {
		std::cerr << "Restarted smoke process did not echo the second payload" << std::endl;
		client.Shutdown();
		return 1;
	}

	client.Shutdown();
	if (client.IsRunning()) {
		std::cerr << "IPC client still reports a running child after shutdown" << std::endl;
		return 1;
	}

	std::cout << "IPC smoke test passed" << std::endl;
	return 0;
}
