add_subdirectory(panels)

set(UI_CORE_SOURCES
    UIManager.cpp
    UIPanel.cpp
)

add_library(editor_ui STATIC ${UI_CORE_SOURCES})

target_include_directories(editor_ui PUBLIC
    ${CMAKE_SOURCE_DIR}/src
    ${CMAKE_SOURCE_DIR}/include
)

target_link_libraries(editor_ui PUBLIC editor_ui_panels)
target_link_libraries(editor_ui PRIVATE deps::engine engine::config)
