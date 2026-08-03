add_library(editor_controller STATIC
    PipelineController.cpp
)

target_include_directories(editor_controller PUBLIC
    ${CMAKE_SOURCE_DIR}/src
)

target_link_libraries(editor_controller
    PUBLIC
        editor_backend
    PRIVATE
        editor_persistence
)
