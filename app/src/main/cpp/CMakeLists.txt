cmake_minimum_required(VERSION 3.22.1)
project(nova_native LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)

add_subdirectory(llama.cpp)

add_library(nova_native SHARED nova_jni.cpp)

target_link_libraries(nova_native
    PRIVATE
    llama
    android
    log
)

target_include_directories(nova_native PRIVATE llama.cpp/include)
