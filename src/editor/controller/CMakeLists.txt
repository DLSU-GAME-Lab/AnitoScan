add_library(editor_controller STATIC
    PipelineController.cpp
)

target_include_directories(editor_controller PUBLIC
    ${CMAKE_SOURCE_DIR}/src
)
