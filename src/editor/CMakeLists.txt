add_subdirectory(render)
add_subdirectory(UI)

set(EDITOR_CORE_SOURCES
    main.cpp
    App.cpp
    IPCClient.cpp
)

add_executable(${MAIN_TARGET} ${EDITOR_CORE_SOURCES})

target_include_directories(${MAIN_TARGET} PRIVATE
    ${CMAKE_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(${MAIN_TARGET} PRIVATE
    editor_render
    editor_ui
    deps::engine
    engine::config
)

add_custom_command(TARGET ${MAIN_TARGET} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        $<TARGET_FILE:SDL2::SDL2>
        $<TARGET_FILE_DIR:${MAIN_TARGET}>
)

set_target_properties(${MAIN_TARGET} PROPERTIES
    VS_DEBUGGER_WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
)

target_compile_definitions(${MAIN_TARGET} PRIVATE
    IMGUI_IMPL_OPENGL_LOADER_GLAD2
    PROJECT_ROOT_DIR="${MY_PROJECT_ROOT}"
)
