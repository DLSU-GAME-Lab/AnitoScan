add_library(engine_config INTERFACE)
add_library(engine::config ALIAS engine_config)

target_compile_definitions(engine_config INTERFACE
    IMGUI_IMPL_OPENGL_LOADER_GLAD2
    PROJECT_ROOT_DIR="${MY_PROJECT_ROOT}"
)

if(MSVC)
    target_compile_options(engine_config INTERFACE /W4 /WX)
else()
    target_compile_options(engine_config INTERFACE -Wall -Wextra)
endif()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin" CACHE INTERNAL "")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin" CACHE INTERNAL "")
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin" CACHE INTERNAL "")
