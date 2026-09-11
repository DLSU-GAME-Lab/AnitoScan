set(FETCHCONTENT_BASE_DIR "${CMAKE_SOURCE_DIR}/vendor")
include(FetchContent)

# ImGUI
FetchContent_Declare(
    imgui
    GIT_REPOSITORY https://github.com/ocornut/imgui.git
    GIT_TAG        v1.92.9b-docking
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
find_package(OpenGL REQUIRED)

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
    GIT_TAG        v2.0.0rc13
    SUBBUILD_DIR   "${CMAKE_SOURCE_DIR}/vendor/tinyobjloader/subbuild"
    SOURCE_DIR     "${CMAKE_SOURCE_DIR}/vendor/tinyobjloader/src"
    BINARY_DIR     "${CMAKE_SOURCE_DIR}/vendor/tinyobjloader/build"
)
FetchContent_MakeAvailable(tinyobjloader)

# GLAD
add_library(glad STATIC "${CMAKE_SOURCE_DIR}/vendor/glad/src/gl.c")
target_include_directories(glad PUBLIC "${CMAKE_SOURCE_DIR}/vendor/glad/include")

set(IMGUI_COMPILE_SOURCES
    ${imgui_SOURCE_DIR}/imgui.cpp
    ${imgui_SOURCE_DIR}/imgui_draw.cpp
    ${imgui_SOURCE_DIR}/imgui_tables.cpp
    ${imgui_SOURCE_DIR}/imgui_widgets.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_sdl2.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_opengl3.cpp
)

add_library(vendor_imgui STATIC ${IMGUI_COMPILE_SOURCES})
add_library(vendor::imgui ALIAS vendor_imgui)

target_include_directories(vendor_imgui PUBLIC
    ${imgui_SOURCE_DIR}
    ${imgui_SOURCE_DIR}/backends
    ${SDL2_SOURCE_DIR}/include
)

target_link_libraries(vendor_imgui PUBLIC
    SDL2::SDL2
    OpenGL::GL
)

# stb
add_library(vendor_stb INTERFACE)
add_library(vendor::stb ALIAS vendor_stb)
target_include_directories(vendor_stb INTERFACE "${CMAKE_SOURCE_DIR}/vendor/stb")
