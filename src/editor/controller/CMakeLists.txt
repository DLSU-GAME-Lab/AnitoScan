set(CONTROLLER_SOURCES
    PipelineController.cpp
)

add_library(editor_controller STATIC ${CONTROLLER_SOURCES})

target_include_directories(editor_controller PUBLIC
    ${CMAKE_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(editor_controller PRIVATE
    editor_ipc
    editor_state
    nlohmann_json::nlohmann_json
)
