#include "IPCClient.h"

#include <iostream>
#include <utility>

#include <nlohmann/json.hpp>

#include "IPCClientPlatform.h"
#include "IPCProtocol.h"

IPCClient::IPCClient()
	: platform(CreateIPCClientPlatform()) {}

IPCClient::~IPCClient() {
	Shutdown();
}

bool IPCClient::Start(const std::string& executable, const std::vector<std::string>& arguments) {
	if (executable.empty()) {
		std::cerr << "[ERROR]: Cannot start backend with an empty executable." << std::endl;
		return false;
	}
	if (IsRunning()) {
		std::cerr << "[ERROR]: Cannot start a backend while another backend is running." << std::endl;
		return false;
	}

	// Join and release resources from a process that exited naturally.
	platform->Shutdown();

	configuredExecutable = executable;
	configuredArguments = arguments;
	hasConfiguration = true;
	backendReady = false;

	{
		std::lock_guard<std::mutex> lock(messageMutex);
		std::queue<BackendMessage> empty;
		queuedMessages.swap(empty);
	}

	std::string error;
	if (!platform->Start(
			executable,
			arguments,
			[this](std::string line) { HandleStdoutLine(std::move(line)); },
			[this](std::string line) { HandleStderrLine(std::move(line)); },
			error)) {
		std::cerr << "[ERROR]: Failed to launch backend: " << error << std::endl;
		return false;
	}

	return true;
}

bool IPCClient::Restart() {
	if (!hasConfiguration) {
		std::cerr << "[ERROR]: Cannot restart backend before it has been configured." << std::endl;
		return false;
	}

	const std::string executable = configuredExecutable;
	const std::vector<std::string> arguments = configuredArguments;
	Shutdown();
	return Start(executable, arguments);
}

bool IPCClient::Send(const std::string& jsonLine) {
	if (!IsRunning()) {
		std::cerr << "[ERROR]: Cannot send a message because the backend is not running." << std::endl;
		return false;
	}

	std::string error;
	if (!platform->Send(jsonLine + "\n", error)) {
		std::cerr << "[ERROR]: Failed to send backend message: " << error << std::endl;
		return false;
	}
	return true;
}

void IPCClient::Poll(std::vector<BackendMessage>& outMessages) {
	std::lock_guard<std::mutex> lock(messageMutex);
	while (!queuedMessages.empty()) {
		outMessages.push_back(std::move(queuedMessages.front()));
		queuedMessages.pop();
	}
}

bool IPCClient::IsRunning() const {
	return platform->IsRunning();
}

void IPCClient::Shutdown() {
	if (platform) {
		platform->Shutdown();
	}
	backendReady = false;
}

void IPCClient::HandleStdoutLine(std::string line) {
	if (line.empty()) {
		return;
	}

	BackendMessage message;
	message.raw = std::move(line);
	message.type = "unknown";

	try {
		const auto json = nlohmann::json::parse(message.raw);
		message.type = json.value("type", "unknown");
		if (message.type == "backend_ready") {
			int version = json.value("protocol_version", -1);
			if (version == IPCProtocol::PROTOCOL_VERSION) {
				backendReady = true;
			} else {
				std::cerr << "[ERROR]: Backend protocol version mismatch. Expected "
				          << IPCProtocol::PROTOCOL_VERSION << " but received " << version << std::endl;
				backendReady = false;
			}
		}
	}
	catch (const nlohmann::json::exception&) {
	}

	std::lock_guard<std::mutex> lock(messageMutex);
	queuedMessages.push(std::move(message));
}

void IPCClient::HandleStderrLine(std::string line) {
	if (!line.empty()) {
		std::cerr << "[BACKEND]: " << line << std::endl;
	}
}
