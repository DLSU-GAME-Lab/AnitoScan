#pragma once

#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <vector>

#include "IPCMessage.h"

class IPCClientPlatform;

class IPCClient {
public:
	IPCClient();
	~IPCClient();

	IPCClient(const IPCClient&) = delete;
	IPCClient& operator=(const IPCClient&) = delete;

	bool Start(const std::string& executable, const std::vector<std::string>& arguments);
	bool Restart();
	bool Send(const std::string& jsonLine);
	void Poll(std::vector<BackendMessage>& outMessages);
	bool IsRunning() const;
	bool IsBackendReady() const { return backendReady; }
	void Shutdown();

private:
	void HandleStdoutLine(std::string line);
	void HandleStderrLine(std::string line);

	std::unique_ptr<IPCClientPlatform> platform;
	std::string configuredExecutable;
	std::vector<std::string> configuredArguments;
	bool hasConfiguration = false;
	bool backendReady = false;

	std::mutex messageMutex;
	std::queue<BackendMessage> queuedMessages;
};
