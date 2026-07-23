# Header-only library for state models
add_library(editor_state INTERFACE)

target_include_directories(editor_state INTERFACE
    ${CMAKE_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}
)
