add_library(editor_ui STATIC
    UIManager.cpp
    screens/PostExportScreen.cpp
    components/Viewport.cpp
)

target_include_directories(editor_ui PUBLIC
    ${CMAKE_SOURCE_DIR}/src
)

target_link_libraries(editor_ui PRIVATE
    vendor::imgui
)
