cmake_minimum_required (VERSION 3.22)
project ("AnitoScan" LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_program(ANITOSCAN_UV_EXECUTABLE NAMES uv REQUIRED)

include(CTest)

set(MY_PROJECT_ROOT "${CMAKE_SOURCE_DIR}" CACHE INTERNAL "")
set(MAIN_TARGET "AnitoScan" CACHE INTERNAL "Main application target name")

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")
include(Dependencies)
include(Config)

add_subdirectory(src/editor)

if(BUILD_TESTING)
    file(STRINGS "${CMAKE_SOURCE_DIR}/.python-version" ANITOSCAN_PYTHON_VERSION LIMIT_COUNT 1)
    string(STRIP "${ANITOSCAN_PYTHON_VERSION}" ANITOSCAN_PYTHON_VERSION)
    if(ANITOSCAN_PYTHON_VERSION STREQUAL "")
        message(FATAL_ERROR ".python-version must contain the dummy test Python version")
    endif()

    add_test(
        NAME dummy_backend_protocol
        COMMAND
            "${ANITOSCAN_UV_EXECUTABLE}"
            run
            --isolated
            --no-project
            --python "${ANITOSCAN_PYTHON_VERSION}"
            --
            python
            -u
            "${CMAKE_SOURCE_DIR}/src/pipeline/tests/test_dummy_backend.py"
    )
    set_tests_properties(dummy_backend_protocol PROPERTIES
        TIMEOUT 120
        WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    )

    add_test(
        NAME python_pipeline_integration
        COMMAND
            "${ANITOSCAN_UV_EXECUTABLE}"
            run
            --isolated
            --no-project
            --python "${ANITOSCAN_PYTHON_VERSION}"
            --
            python
            -u
            -m
            unittest
            src.pipeline.tests.test_pipeline
            src.pipeline.tests.test_backend
    )
    set_tests_properties(python_pipeline_integration PROPERTIES
        TIMEOUT 30
        WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    )
endif()
