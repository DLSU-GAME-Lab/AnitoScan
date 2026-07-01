#pragma once

#include <stdexcept>
#include <windows.h>
#include <string>
#include <mutex>
#include <thread>
#include <atomic>
#include <functional>
#include <queue>

#include "Types.h"
#include "nlohmann/json.hpp"


class IPCClient {
public:
	IPCClient();
	~IPCClient();

	bool Start(const String& pythonExe, const String& scriptPath);
	void Send(const String& jsonLine);
	void Poll(std::vector<BackendMessage>& outMessages);
	bool IsRunning();
	void Shutdown();

private:
	void RenderThread();

private:
	HANDLE hProcess;
	HANDLE hStdin;
	HANDLE hStdout;

	std::thread thread;
	std::atomic<bool> running;
	std::mutex mutex;
	std::queue<BackendMessage> qMessages;
};
