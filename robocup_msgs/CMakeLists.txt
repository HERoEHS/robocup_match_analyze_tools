cmake_minimum_required(VERSION 3.5)
project(robocup_msgs)

# Add C++ standard
set(CMAKE_CXX_STANDARD 17)

# ###############################################################################
# Dependencies
# ###############################################################################
find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)

include_directories(
  include
)

# ###############################################################################
# Declare ROS messages, services, and actions
# ###############################################################################
set(msg_files
  "msg/FoundObject.msg"
  "msg/FoundObjectArray.msg"
  "msg/FoundMatched.msg"
  "msg/FoundMatchedArray.msg"
  "msg/MoveCommand.msg"
  "msg/ProtoBufBallData.msg"
  "msg/ProtoBufRobotData.msg"
  "msg/RoboCupGameControlRosData.msg" 
  "msg/RoboCupGameControlRosReturnData.msg"
  "msg/RoboCupRobotData.msg"
  "msg/RobotRosInfo.msg"
  "msg/TeamRosInfo.msg"
  "msg/MultiRobotBallData.msg"
  "msg/NamedPose.msg"
  "msg/GlobalBallWithCovariance.msg"
  "msg/ObservedRobotArray.msg"
)

set(srv_files
)

set(action_files
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${msg_files}
  ${srv_files}
  ${action_files}
  DEPENDENCIES
  builtin_interfaces
  std_msgs
  sensor_msgs
  geometry_msgs
)

add_library(robocup_ros_bridge src/robocup_ros_bridge.cpp)
add_dependencies(robocup_ros_bridge ${PROJECT_NAME})

# 시스템 아키텍처를 확인합니다.
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64")
  # aarch64(ARM 아키텍처)인 경우
  rosidl_target_interfaces(robocup_ros_bridge ${PROJECT_NAME} rosidl_typesupport_cpp)
else()
  # 그 외(X64 등)인 경우
  rosidl_get_typesupport_target(cpp_typesupport_target ${PROJECT_NAME} rosidl_typesupport_cpp)
  target_link_libraries(robocup_ros_bridge ${cpp_typesupport_target})
endif()

ament_target_dependencies(robocup_ros_bridge rclcpp)

ament_export_targets(export_robocup_ros_bridge HAS_LIBRARY_TARGET)
ament_export_dependencies(rosidl_default_runtime)

install(DIRECTORY
  include/
  DESTINATION include/
)

install(TARGETS
  robocup_ros_bridge
  DESTINATION lib/${PROJECT_NAME}
)

install(
  TARGETS robocup_ros_bridge
  EXPORT export_robocup_ros_bridge
  LIBRARY DESTINATION lib
  ARCHIVE DESTINATION lib
  RUNTIME DESTINATION bin
  INCLUDES DESTINATION include
)

ament_package()
