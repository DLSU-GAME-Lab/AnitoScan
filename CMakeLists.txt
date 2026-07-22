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
