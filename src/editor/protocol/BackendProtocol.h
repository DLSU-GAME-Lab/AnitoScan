#pragma once

#include <optional>
#include <string>
#include <string_view>

struct ProtocolMessage {
    std::string type;
    std::string value;
};

std::string SerializeMessage(
    std::string_view type,
    std::string_view value
);

std::optional<ProtocolMessage> ParseMessage(
    std::string_view json
);
