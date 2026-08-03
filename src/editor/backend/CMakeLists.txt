add_library(editor_backend STATIC
    BackendProtocol.cpp
)

target_include_directories(editor_backend PUBLIC
    ${CMAKE_SOURCE_DIR}/src
)

target_link_libraries(editor_backend PRIVATE
    nlohmann_json::nlohmann_json
)
