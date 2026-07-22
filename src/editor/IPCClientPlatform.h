#pragma once

#include <functional>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

class IPCClientPlatform {
public:
	using LineHandler = std::function<void(std::string)>;

	virtual ~IPCClientPlatform() = default;

	virtual bool Start(
		const std::string& executable,
		const std::vector<std::string>& arguments,
		LineHandler stdoutHandler,
		LineHandler stderrHandler,
		std::string& error) = 0;
	virtual bool Send(std::string_view data, std::string& error) = 0;
	virtual bool IsRunning() const = 0;
	virtual void Shutdown() = 0;
};

std::unique_ptr<IPCClientPlatform> CreateIPCClientPlatform();
