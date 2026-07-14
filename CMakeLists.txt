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

# glm
FetchContent_Declare(
    glm
    GIT_REPOSITORY https://github.com/g-truc/glm.git
    GIT_TAG        1.0.1
    SUBBUILD_DIR   "${CMAKE_SOURCE_DIR}/vendor/glm/subbuild"
    SOURCE_DIR     "${CMAKE_SOURCE_DIR}/vendor/glm/src"
    BINARY_DIR     "${CMAKE_SOURCE_DIR}/vendor/glm/build"
)
FetchContent_MakeAvailable(glm)

# tinyobjloader
FetchContent_Declare(
    tinyobjloader
    GIT_REPOSITORY https://github.com/tinyobjloader/tinyobjloader.git
    GIT_TAG        release
    SUBBUILD_DIR   "${CMAKE_SOURCE_DIR}/vendor/tinyobjloader/subbuild"
    SOURCE_DIR     "${CMAKE_SOURCE_DIR}/vendor/tinyobjloader/src"
    BINARY_DIR     "${CMAKE_SOURCE_DIR}/vendor/tinyobjloader/build"
)
FetchContent_MakeAvailable(tinyobjloader)

add_library(glad STATIC
    "${CMAKE_SOURCE_DIR}/vendor/glad/src/gl.c"
)

target_include_directories(glad PUBLIC
    "${CMAKE_SOURCE_DIR}/vendor/glad/include"
)


# TODO: complete when editor is now included
add_executable(${PROJECT_NAME}
    src/editor/main.cpp
    src/editor/App.cpp
    src/editor/IPCClient.cpp 

    src/editor/UI/UIManager.cpp 
    src/editor/UI/UIPanel.cpp
    src/editor/UI/panels/DockSpace.cpp
    src/editor/UI/panels/OverviewPanel.cpp
    src/editor/UI/panels/FileViewer.cpp
    src/editor/UI/panels/LogPanel.cpp
    src/editor/UI/panels/MaskingPopup.cpp
    src/editor/UI/panels/ViewportPanel.cpp
    src/editor/UI/panels/InputWindow.cpp

    src/editor/render/Shader.cpp
    src/editor/render/Mesh.cpp
    src/editor/render/Model.cpp
    src/editor/render/Camera.cpp
    src/editor/render/Scene.cpp
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
# "src/editor/render/Mesh.h"
)


target_include_directories(${PROJECT_NAME} PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    "${CMAKE_SOURCE_DIR}/src"
    "${imgui_SOURCE_DIR}"
    "${imgui_SOURCE_DIR}/backends"
    "${SDL2_SOURCE_DIR}/include"
    "${nlohmann_json_SOURCE_DIR}/include"
    "${CMAKE_SOURCE_DIR}/vendor/stb"
    "${CMAKE_SOURCE_DIR}/vendor/imgui/src"
    "${CMAKE_SOURCE_DIR}/vendor/imfilebrowser"
    "${tinyobjloader_SOURCE_DIR}"
)

target_link_libraries(${PROJECT_NAME} PRIVATE
    SDL2::SDL2
    SDL2::SDL2main
    opengl32
    nlohmann_json::nlohmann_json
    glm::glm
    glad
)

add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        $<TARGET_FILE:SDL2::SDL2>
        $<TARGET_FILE_DIR:${PROJECT_NAME}>
)

set_target_properties(${PROJECT_NAME} PROPERTIES
    VS_DEBUGGER_WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

target_compile_definitions(${PROJECT_NAME} PRIVATE
    IMGUI_IMPL_OPENGL_LOADER_GLAD2
    PROJECT_ROOT_DIR="${CMAKE_SOURCE_DIR}"
)