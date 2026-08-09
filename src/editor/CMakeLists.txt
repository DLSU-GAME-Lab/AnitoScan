add_subdirectory(protocol)
add_subdirectory(backend)
add_subdirectory(persistence)
add_subdirectory(controller)
add_subdirectory(render)
add_subdirectory(ui)

add_executable(${MAIN_TARGET}
    main.cpp
    App.cpp
)

target_include_directories(${MAIN_TARGET} PRIVATE
    ${CMAKE_SOURCE_DIR}/src
)

target_link_libraries(${MAIN_TARGET} PRIVATE
    editor_backend
    editor_controller
    editor_persistence
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
