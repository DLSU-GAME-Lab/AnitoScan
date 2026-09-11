add_library(editor_ui STATIC
    UIManager.cpp
    UIStyle.cpp
    screens/RunSetupScreen.cpp
    screens/PhaseScreen.cpp
    screens/PostExportScreen.cpp
    components/Viewport.cpp
    components/LogView.cpp
    components/RunControls.cpp
    components/RunSelector.cpp
    components/MaskingContent.cpp
    components/ExportContent.cpp
)

target_include_directories(editor_ui PUBLIC
    ${CMAKE_SOURCE_DIR}/src
)

target_link_libraries(editor_ui
    PUBLIC
        SDL2::SDL2
    PRIVATE
        glad
        vendor::imgui
        vendor::stb
)
