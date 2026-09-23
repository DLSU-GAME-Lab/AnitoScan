add_library(editor_protocol STATIC
    BackendProtocol.cpp
)

target_include_directories(editor_protocol PUBLIC
    ${CMAKE_SOURCE_DIR}/src
)

target_link_libraries(editor_protocol PRIVATE
    nlohmann_json::nlohmann_json
)
