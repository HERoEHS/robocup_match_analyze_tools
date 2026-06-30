cmake_minimum_required(VERSION 3.8)
project(robocup_blackbox)

if(NOT DEFINED CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rosbag2_cpp REQUIRED)
find_package(rosbag2_storage_mcap REQUIRED)
find_package(std_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(tf2_msgs REQUIRED)
find_package(yaml-cpp REQUIRED)

include_directories(
  include
  ${YAML_CPP_INCLUDE_DIRS}
)

add_library(${PROJECT_NAME}
  src/topic_config.cpp
  src/throttle_queue.cpp
  src/mcap_writer.cpp
  src/watchdog.cpp
)

ament_target_dependencies(${PROJECT_NAME}
  rclcpp
  rosbag2_cpp
  std_msgs
  diagnostic_msgs
  geometry_msgs
  sensor_msgs
  tf2_msgs
  yaml-cpp
)

target_link_libraries(${PROJECT_NAME}
  ${YAML_CPP_LIBRARIES}
)

# Executables
add_executable(blackbox_writer_node src/blackbox_writer_node.cpp)
target_link_libraries(blackbox_writer_node ${PROJECT_NAME})
ament_target_dependencies(blackbox_writer_node
  rclcpp
  rosbag2_cpp
  std_msgs
  diagnostic_msgs
  geometry_msgs
  sensor_msgs
  tf2_msgs
  yaml-cpp
)

# Install
install(TARGETS ${PROJECT_NAME} blackbox_writer_node
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY include/
  DESTINATION include
)

install(DIRECTORY config launch scripts
  DESTINATION share/${PROJECT_NAME}
)

install(PROGRAMS
  scripts/web_download
  scripts/web_dashboard.py
  DESTINATION lib/${PROJECT_NAME}
)

# Testing
if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_throttle_queue test/test_throttle_queue.cpp)
  target_link_libraries(test_throttle_queue ${PROJECT_NAME})
  
  ament_add_gtest(test_mcap_write test/test_mcap_write.cpp)
  target_link_libraries(test_mcap_write ${PROJECT_NAME})
endif()

ament_export_include_directories(include)
ament_export_libraries(${PROJECT_NAME})
ament_package()
