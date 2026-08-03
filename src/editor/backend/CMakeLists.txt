find_package(Threads REQUIRED)

add_library(editor_backend STATIC
    BackendClient.cpp
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
    Threads::Threads
)
