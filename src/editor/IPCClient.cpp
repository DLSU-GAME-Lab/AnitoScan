#include "IPCClient.h"
#include <iostream>

// Initializes all process and pipe handles to invalid states
IPCClient::IPCClient() {
	this->hProcess = INVALID_HANDLE_VALUE;
	this->hStdin = INVALID_HANDLE_VALUE;
	this->hStdout = INVALID_HANDLE_VALUE;

}

IPCClient::~IPCClient() {}

void IPCClient::RunThroughUV(std::filesystem::path pythonSource) {
	std::string uvExecutable = "uv";

	std::filesystem::path projectRoot(PROJECT_ROOT_DIR);

	std::filesystem::path pythonScript = projectRoot / pythonSource;

	std::string commandArgs = "run python \"" + pythonScript.string() + "\" --ipc";

	std::cout << "[DEBUG] Spawning process manager: " << uvExecutable << std::endl;
	std::cout << "[DEBUG] UV Run Arguments: " << commandArgs << std::endl;

	// 5. Start the process via UV
	if (!Start(uvExecutable.c_str(), commandArgs.c_str())) {
		std::cerr << "[ERROR]: Failed to launch UV package manager backend." << std::endl;
	}
}


// Starts a Python subprocess and sets up inter-process communication (IPC) using pipes for stdin and stdout
// Redirects the child process I/O so the application can send commands and receive responses
// Also launches a background thread to continuously read output from the process
bool IPCClient::Start(const String& pythonExe, const String& scriptPath) {
	HANDLE stdinRead, stdinWrite;
	HANDLE stdoutRead, stdoutWrite;

	SECURITY_ATTRIBUTES sa{ sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE };
	if (!CreatePipe(&stdinRead, &stdinWrite, &sa, 0)) {
		return false;
	}
	if (!CreatePipe(&stdoutRead, &stdoutWrite, &sa, 0)) {
		return false;
	}

	SetHandleInformation(stdinWrite, HANDLE_FLAG_INHERIT, 0);
	SetHandleInformation(stdoutRead, HANDLE_FLAG_INHERIT, 0);

	//build
	String cmd = pythonExe + " " + scriptPath;
	std::vector<char> cmdBuf(cmd.begin(), cmd.end());
	cmdBuf.push_back('\0');

	STARTUPINFOA si{};
	si.cb = sizeof(si);
	si.dwFlags = STARTF_USESTDHANDLES;
	si.hStdInput = stdinRead;
	si.hStdOutput = stdoutWrite;
	si.hStdError = stdoutWrite;

	PROCESS_INFORMATION pi{};

	this->hJob = CreateJobObjectA(nullptr, nullptr);
	JOBOBJECT_EXTENDED_LIMIT_INFORMATION jeli{};
	jeli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
	SetInformationJobObject(this->hJob, JobObjectExtendedLimitInformation, &jeli, sizeof(jeli));

	BOOL ok = CreateProcessA(
		nullptr, cmdBuf.data(),
		nullptr, nullptr,
		TRUE,
		CREATE_NO_WINDOW,
		nullptr, nullptr,
		&si, &pi
	);

	AssignProcessToJobObject(this->hJob, pi.hProcess);

	CloseHandle(stdinRead);
	CloseHandle(stdoutWrite);

	if (!ok) return false;

	CloseHandle(pi.hThread);
	this->hProcess = pi.hProcess;
	this->hStdin = stdinWrite;
	this->hStdout = stdoutRead;

	// background reader thread
	this->running = true;
	this->thread = std::thread(&IPCClient::RenderThread, this);

	return true;
}

// Sends a JSON-formatted message to the subprocess via stdin
void IPCClient::Send(const String& jsonLine) {
	String line = jsonLine + "\n";
	DWORD written = 0;
	WriteFile(this->hStdin, line.c_str(), (DWORD)line.size(), &written, nullptr);
}

// Retrieves all pending messages received from the subprocess
void IPCClient::Poll(std::vector<BackendMessage>& outMessages) {
	std::lock_guard<std::mutex> lock(mutex);
	while (!this->qMessages.empty()) {
		outMessages.push_back(std::move(this->qMessages.front()));
		this->qMessages.pop();
	}
}

bool IPCClient::IsRunning() {
	return true;
}

// Background thread function that continuously reads stdout from the subprocess
void IPCClient::RenderThread() {
	String lineBuf;
	char ch = 0;

	DWORD bytesRead = 0;
	while (true) {
		BOOL ok = ReadFile(this->hStdout, &ch, 1, &bytesRead, nullptr);
		if (!ok || bytesRead == 0) break;

		if (ch == '\n') {
			if (!lineBuf.empty()) {
					BackendMessage msg;
					msg.raw = lineBuf;
					msg.type = "unknown";
				try {
					auto j = nlohmann::json::parse(lineBuf);
					msg.type = j.value("type", "unknown");
				}
				catch (const nlohmann::json::exception&) {

				}

				{
					std::lock_guard<std::mutex> lock(this->mutex);
					this->qMessages.push(std::move(msg));
				}
			}
			lineBuf.clear();
		}
		else {
			lineBuf += ch;
		}
		
	}

	this->running = false;
}

void IPCClient::Shutdown() {
	if (this->hJob) {
		TerminateJobObject(this->hJob, 0);
		CloseHandle(this->hJob);
		this->hJob = nullptr;
	}

	if (this->hProcess != INVALID_HANDLE_VALUE) {
		TerminateProcess(this->hProcess, 0);
	}

	if (this->hStdin != INVALID_HANDLE_VALUE) {
		CloseHandle(this->hStdin);
		this->hStdin = INVALID_HANDLE_VALUE;
	}

	if (this->thread.joinable()) {
		this->thread.join();
	}

	if (this->hProcess != INVALID_HANDLE_VALUE) {
		CloseHandle(this->hProcess);
		this->hProcess = INVALID_HANDLE_VALUE;
	}

	if (this->hStdout != INVALID_HANDLE_VALUE) {
		CloseHandle(this->hStdout);
		this->hStdout = INVALID_HANDLE_VALUE;
	}
}
