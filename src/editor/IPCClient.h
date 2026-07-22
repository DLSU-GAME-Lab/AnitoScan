#pragma once

#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <vector>

#include "IPCMessage.h"

class IPCClientPlatform;

// Start, Restart, and Shutdown are main-thread lifecycle operations. Send and
// Poll synchronize their own transport/message access.
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
	void Shutdown();

private:
	void HandleStdoutLine(std::string line);
	void HandleStderrLine(std::string line);

	std::unique_ptr<IPCClientPlatform> platform;
	std::string configuredExecutable;
	std::vector<std::string> configuredArguments;
	bool hasConfiguration = false;

	std::mutex messageMutex;
	std::queue<BackendMessage> queuedMessages;
};
