#define ROBOCUP_MSGS_ROBOCUP_ROS_BRIDGE_HPP
#ifdef ROBOCUP_MSGS_ROBOCUP_ROS_BRIDGE_HPP

#include "rclcpp/rclcpp.hpp"
#include <algorithm>
#include <cstring>
#include "robocup_msgs/RoboCupGameControlData.h"

#include "robocup_msgs/msg/robo_cup_game_control_ros_data.hpp"
#include "robocup_msgs/msg/robo_cup_game_control_ros_return_data.hpp"

namespace robocup
{

  void PrintControlData(RoboCupGameControlData &control_data);
  void PrintTeamInfo(TeamInfo &team);
  void PrintRobotInfo(RobotInfo &player);

  void SetRoboCupGameControlRosData(robocup_msgs::msg::RoboCupGameControlRosData &data, const RoboCupGameControlData &src, const int team_index, const int robot_index);
  void SetRoboCupGameControlRosData(robocup_msgs::msg::RoboCupGameControlRosData &data, const RoboCupGameControlData &src);
  void SetRoboCupGameControlRosReturnData(robocup_msgs::msg::RoboCupGameControlRosReturnData &data, const RoboCupGameControlReturnData &src);
  void SetTeamRosInfo(robocup_msgs::msg::TeamRosInfo &info, const TeamInfo &src);
  void SetRobotRosInfo(robocup_msgs::msg::RobotRosInfo &info, const RobotInfo &src);

  void SetRoboCupGameControlData(RoboCupGameControlData &data, const robocup_msgs::msg::RoboCupGameControlRosData &src);
  void SetRoboCupGameControlReturnData(RoboCupGameControlReturnData &data, const robocup_msgs::msg::RoboCupGameControlRosReturnData &src);
  void SetTeamInfo(TeamInfo &info, const robocup_msgs::msg::TeamRosInfo &src);
  void SetRobotInfo(RobotInfo &info, const robocup_msgs::msg::RobotRosInfo &src);

} // namespace robocup

#endif
