set(RENDER_SOURCES
    Shader.cpp
    Mesh.cpp
    Model.cpp
    Camera.cpp
    Scene.cpp
)

add_library(editor_render STATIC ${RENDER_SOURCES})

target_include_directories(editor_render PUBLIC
    ${CMAKE_SOURCE_DIR}/src
)

target_link_libraries(editor_render
    PUBLIC
        glad
        glm::glm
        tinyobjloader
        vendor::stb
    PRIVATE
        OpenGL::GL
        engine::config
)
