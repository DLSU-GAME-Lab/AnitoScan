#include <cassert>
#include <iostream>
#include "IPCProtocol.h"

void TestCommandSerialization() {
	std::string runCmd = IPCProtocol::SerializeRunPipeline("test_run", "input.mp4", 45, "fast");
	auto jRun = nlohmann::json::parse(runCmd);
	assert(jRun["type"] == "run_pipeline");
	assert(jRun["run_name"] == "test_run");
	assert(jRun["input"] == "input.mp4");
	assert(jRun["minimum_frames"] == 45);
	assert(jRun["quality"] == "fast");

	std::string selCmd = IPCProtocol::SerializeSelection("req-123", 2);
	auto jSel = nlohmann::json::parse(selCmd);
	assert(jSel["type"] == "selection");
	assert(jSel["request_id"] == "req-123");
	assert(jSel["choice"] == 2);

	std::string skipCmd = IPCProtocol::SerializeSelectionSkip("req-123");
	auto jSkip = nlohmann::json::parse(skipCmd);
	assert(jSkip["type"] == "selection");
	assert(jSkip["request_id"] == "req-123");
	assert(jSkip["choice"] == "skip");

	std::string cancelCmd = IPCProtocol::SerializeCancelPipeline("test_run");
	auto jCancel = nlohmann::json::parse(cancelCmd);
	assert(jCancel["type"] == "cancel_pipeline");
	assert(jCancel["run_name"] == "test_run");
}

void TestEventDecoding() {
	std::string readyJson = R"({"type":"backend_ready","protocol_version":1})";
	auto ready = IPCProtocol::DecodeEvent(readyJson);
	assert(ready.type == IPCProtocol::EventType::BACKEND_READY);
	assert(ready.backendReady.protocolVersion == 1);

	std::string workspaceJson = R"({"type":"workspace_ready","run_name":"r1","workspace":"/tmp/exact-workspace"})";
	auto workspace = IPCProtocol::DecodeEvent(workspaceJson);
	assert(workspace.type == IPCProtocol::EventType::WORKSPACE_READY);
	assert(workspace.workspaceReady.workspace == "/tmp/exact-workspace");

	std::string missingWorkspaceJson = R"({"type":"workspace_ready","run_name":"r1"})";
	auto missingWorkspace = IPCProtocol::DecodeEvent(missingWorkspaceJson);
	assert(missingWorkspace.type == IPCProtocol::EventType::UNKNOWN);

	std::string emptyWorkspaceJson = R"({"type":"workspace_ready","run_name":"r1","workspace":""})";
	auto emptyWorkspace = IPCProtocol::DecodeEvent(emptyWorkspaceJson);
	assert(emptyWorkspace.type == IPCProtocol::EventType::UNKNOWN);

	std::string progressJson = R"({"type":"progress","phase":1,"value":0.5,"overall_value":0.1,"label":"Extracting"})";
	auto prog = IPCProtocol::DecodeEvent(progressJson);
	assert(prog.type == IPCProtocol::EventType::PROGRESS);
	assert(prog.progress.phase == Phase::CAPTURE);
	assert(prog.progress.value == 0.5f);
	assert(prog.progress.overallValue == 0.1f);
	assert(prog.progress.label == "Extracting");

	std::string doneJson = R"({"type":"done","run_name":"r1","workspace":"ws","output":"data/output/r1/model.obj"})";
	auto done = IPCProtocol::DecodeEvent(doneJson);
	assert(done.type == IPCProtocol::EventType::DONE);
	assert(done.done.runName == "r1");
	assert(done.done.output == "data/output/r1/model.obj");

	std::string errJson = R"({"type":"error","scope":"run","code":"fail","text":"Error occurred","run_name":"r1","phase":2})";
	auto err = IPCProtocol::DecodeEvent(errJson);
	assert(err.type == IPCProtocol::EventType::ERROR);
	assert(err.error.scope == "run");
	assert(err.error.phase == Phase::MASKING);
}

int main() {
	TestCommandSerialization();
	TestEventDecoding();
	std::cout << "[SUCCESS]: All IPCProtocol C++ tests passed!" << std::endl;
	return 0;
}
