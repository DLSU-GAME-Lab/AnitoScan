cmake_minimum_required (VERSION 3.22)
project ("AnitoScan" LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(FETCHCONTENT_BASE_DIR "${CMAKE_SOURCE_DIR}/vendor")
include(FetchContent)

# ImGUI
FetchContent_Declare(
    imgui
    GIT_REPOSITORY https://github.com/ocornut/imgui.git
    GIT_TAG        docking
    SUBBUILD_DIR   "${CMAKE_SOURCE_DIR}/vendor/imgui/subbuild"
    SOURCE_DIR     "${CMAKE_SOURCE_DIR}/vendor/imgui/src"
    BINARY_DIR     "${CMAKE_SOURCE_DIR}/vendor/imgui/build"
)
FetchContent_MakeAvailable(imgui)

# SDL2
FetchContent_Declare(
    SDL2
    GIT_REPOSITORY https://github.com/libsdl-org/SDL.git
    GIT_TAG        release-2.30.12
    SUBBUILD_DIR   "${CMAKE_SOURCE_DIR}/vendor/SDL2/subbuild"
    SOURCE_DIR     "${CMAKE_SOURCE_DIR}/vendor/SDL2/src"
    BINARY_DIR     "${CMAKE_SOURCE_DIR}/vendor/SDL2/build"
)
FetchContent_MakeAvailable(SDL2)

# nlohmann/json
FetchContent_Declare(
    nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG        v3.11.3
    SUBBUILD_DIR   "${CMAKE_SOURCE_DIR}/vendor/nlohmann_json/subbuild"
    SOURCE_DIR     "${CMAKE_SOURCE_DIR}/vendor/nlohmann_json/src"
    BINARY_DIR     "${CMAKE_SOURCE_DIR}/vendor/nlohmann_json/build"
)
FetchContent_MakeAvailable(nlohmann_json)


# TODO: complete when editor is now included
add_executable(${PROJECT_NAME}
    src/editor/main.cpp
    src/editor/App.cpp
    src/editor/IPCClient.cpp 
    src/editor/UI/UIManager.cpp 
    src/editor/UI/UIPanel.cpp
    src/editor/UI/panels/DockSpace.cpp
    src/editor/UI/panels/OverviewPanel.cpp
    src/editor/UI/panels/InputPanel.cpp
    src/editor/UI/panels/FileViewer.cpp
    src/editor/UI/panels/LogPanel.cpp
    # Add your other .cpp files here

    ${imgui_SOURCE_DIR}/imgui.cpp
    ${imgui_SOURCE_DIR}/imgui_draw.cpp
    ${imgui_SOURCE_DIR}/imgui_tables.cpp
    ${imgui_SOURCE_DIR}/imgui_widgets.cpp
    ${imgui_SOURCE_DIR}/imgui_demo.cpp 
    ${imgui_SOURCE_DIR}/backends/imgui_impl_sdl2.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_opengl3.cpp
#    "src/editor/panels/ScanPanel.h" "src/editor/panels/ScanPanel.cpp" "src/editor/App.h" "src/editor/IPCClient.h" "src/editor/IPCClient.cpp" "src/editor/UI/UIPanel.cpp"
#    "src/editor/Types.h")
)

target_include_directories(${PROJECT_NAME} PRIVATE
    "${CMAKE_SOURCE_DIR}/src"
    "${imgui_SOURCE_DIR}"
    "${imgui_SOURCE_DIR}/backends"
    "${SDL2_SOURCE_DIR}/include"
    "${nlohmann_json_SOURCE_DIR}/include"
    "${CMAKE_SOURCE_DIR}/vendor/stb"
)

target_link_libraries(${PROJECT_NAME} PRIVATE
    SDL2::SDL2
    SDL2::SDL2main
    opengl32
    nlohmann_json::nlohmann_json
)

add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        $<TARGET_FILE:SDL2::SDL2>
        $<TARGET_FILE_DIR:${PROJECT_NAME}>
)