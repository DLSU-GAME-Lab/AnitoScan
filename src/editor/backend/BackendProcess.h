#pragma once

#include <filesystem>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

class BackendProcess {
public:
    BackendProcess();
    ~BackendProcess();

    BackendProcess(const BackendProcess&) = delete;
    BackendProcess& operator=(const BackendProcess&) = delete;

    bool Start(const std::filesystem::path& executable,
               const std::vector<std::string>& arguments,
               const std::filesystem::path& workingDirectory);
    void Stop();
    bool WriteLine(std::string_view line);
    bool ReadStdoutLine(std::string& line);
    bool ReadStderrLine(std::string& line);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
