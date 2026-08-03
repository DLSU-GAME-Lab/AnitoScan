add_library(editor_backend STATIC
    BackendProtocol.cpp
)

if(WIN32)
    target_sources(editor_backend PRIVATE BackendProcessWindows.cpp)
else()
    target_sources(editor_backend PRIVATE BackendProcessPosix.cpp)
endif()

target_include_directories(editor_backend PUBLIC
    ${CMAKE_SOURCE_DIR}/src
)

target_link_libraries(editor_backend PRIVATE
    nlohmann_json::nlohmann_json
)
