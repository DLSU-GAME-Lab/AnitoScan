set(PANEL_SOURCES
    DockSpace.cpp
    OverviewPanel.cpp
    FileViewer.cpp
    LogPanel.cpp
    MaskingPopup.cpp
    ViewportPanel.cpp
    InputWindow.cpp
    MenuToolbar.cpp
)

add_library(editor_ui_panels STATIC ${PANEL_SOURCES})

target_include_directories(editor_ui_panels PUBLIC
    ${CMAKE_SOURCE_DIR}/src
    ${CMAKE_SOURCE_DIR}/include
)

target_link_libraries(editor_ui_panels PRIVATE deps::engine engine::config)
