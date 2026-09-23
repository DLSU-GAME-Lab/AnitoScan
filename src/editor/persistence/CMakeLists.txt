add_library(editor_persistence STATIC
    RunStore.cpp
)

target_include_directories(editor_persistence PUBLIC
    ${CMAKE_SOURCE_DIR}/src
)

target_link_libraries(editor_persistence PRIVATE
    nlohmann_json::nlohmann_json
)
