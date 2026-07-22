add_subdirectory(render)
add_subdirectory(UI)

if(WIN32)
    set(IPC_PLATFORM_SOURCE IPCClientWin32.cpp)
else()
    set(IPC_PLATFORM_SOURCE IPCClientPosix.cpp)
endif()

add_library(editor_ipc STATIC
    IPCClient.cpp
    ${IPC_PLATFORM_SOURCE}
)

target_include_directories(editor_ipc PUBLIC
    ${CMAKE_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(editor_ipc PRIVATE
    Threads::Threads
    nlohmann_json::nlohmann_json
)

if(WIN32)
    target_compile_definitions(editor_ipc PRIVATE _WIN32_WINNT=0x0601)
endif()

add_library(editor_backend_config STATIC BackendLaunchConfig.cpp)
target_include_directories(editor_backend_config PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(editor_backend_config PRIVATE engine::config)

set(EDITOR_CORE_SOURCES
    main.cpp
    App.cpp
)

add_executable(${MAIN_TARGET} ${EDITOR_CORE_SOURCES})

target_include_directories(${MAIN_TARGET} PRIVATE
    ${CMAKE_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(${MAIN_TARGET} PRIVATE
    editor_backend_config
    editor_ipc
    editor_render
    editor_ui
    deps::engine
    engine::config
)

if(WIN32)
    add_custom_command(TARGET ${MAIN_TARGET} POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            $<TARGET_FILE:SDL2::SDL2>
            $<TARGET_FILE_DIR:${MAIN_TARGET}>
    )
endif()

if(MSVC)
    set_target_properties(${MAIN_TARGET} PROPERTIES
        VS_DEBUGGER_WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    )
endif()

target_compile_definitions(${MAIN_TARGET} PRIVATE
    IMGUI_IMPL_OPENGL_LOADER_GLAD2
    PROJECT_ROOT_DIR="${MY_PROJECT_ROOT}"
)

if(BUILD_TESTING)
    add_executable(IPCClientSmokeTest
        tests/IPCClientSmokeTest.cpp
    )
    target_link_libraries(IPCClientSmokeTest PRIVATE
        editor_ipc
        engine::config
    )
    add_test(NAME ipc_transport_smoke COMMAND IPCClientSmokeTest)
    set_tests_properties(ipc_transport_smoke PROPERTIES TIMEOUT 120)

    add_executable(BackendLaunchConfigTest
        tests/BackendLaunchConfigTest.cpp
    )
    target_link_libraries(BackendLaunchConfigTest PRIVATE
        editor_backend_config
        engine::config
    )
    add_test(NAME backend_launch_config COMMAND BackendLaunchConfigTest)
endif()
