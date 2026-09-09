cmake_minimum_required(VERSION 3.21)
project(plotbench-qtgraphs-cpp VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Qt6 6.8 REQUIRED COMPONENTS Core Gui Network WebSockets Quick QuickControls2 Graphs Test)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  find_package(Qt6 6.8 REQUIRED COMPONENTS WaylandClient)
endif()
qt_standard_project_setup(REQUIRES 6.8)

add_library(plotbench_qtgraphs_core STATIC
  src/protocol.cpp
  src/frame_source.cpp
  src/metrics_sink.cpp
  src/image_provider.cpp
  src/resource_usage.cpp
)
target_include_directories(plotbench_qtgraphs_core PUBLIC src)
target_link_libraries(plotbench_qtgraphs_core PUBLIC Qt6::Core Qt6::Gui Qt6::Network Qt6::WebSockets Qt6::Quick)

qt_add_executable(plotbench-qtgraphs-cpp src/main.cpp src/controller.cpp)
set_target_properties(plotbench-qtgraphs-cpp PROPERTIES MACOSX_BUNDLE FALSE WIN32_EXECUTABLE FALSE)
qt_add_qml_module(plotbench-qtgraphs-cpp
  URI PlotbenchQtGraphsCpp
  VERSION 1.0
  QML_FILES Main.qml
)
target_compile_definitions(plotbench-qtgraphs-cpp PRIVATE
  PLOTBENCH_APP_VERSION="${PROJECT_VERSION}"
  PLOTBENCH_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
)
target_link_libraries(plotbench-qtgraphs-cpp PRIVATE plotbench_qtgraphs_core Qt6::QuickControls2 Qt6::Graphs)

enable_testing()
qt_add_executable(plotbench-qtgraphs-cpp-tests tests/test_protocol.cpp)
set_target_properties(plotbench-qtgraphs-cpp-tests PROPERTIES MACOSX_BUNDLE FALSE)
target_link_libraries(plotbench-qtgraphs-cpp-tests PRIVATE plotbench_qtgraphs_core Qt6::Test)
add_test(NAME protocol COMMAND plotbench-qtgraphs-cpp-tests)
add_test(NAME runtime-info COMMAND plotbench-qtgraphs-cpp --runtime-info)
