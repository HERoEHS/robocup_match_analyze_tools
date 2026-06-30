"""Launch a single robocup_udp_sender node.

Run one instance per robot (pass robot_id as a launch argument).
The node subscribes to /robocup_{robot_id}/udp/data and
/robocup_{robot_id}/cooperative_perception/enemies, then broadcasts
MessageV2 UDP packets so UdpTeamListener (strategy GUI) can receive them.

Example:
  ros2 launch robocup_realtime_monitoring robocup_udp_sender.launch.py robot_id:=1
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    args = [
        DeclareLaunchArgument('robot_id', default_value='1',
                               description='Robot player ID (1-7)'),
        DeclareLaunchArgument('team_number', default_value='25',
                               description='Team number; UDP port = 10000 + team_number'),
        DeclareLaunchArgument('udp_broadcast_addr', default_value='127.0.0.1',
                               description='UDP broadcast address'),
        DeclareLaunchArgument('role', default_value='1',
                               description='Robot role: 1=player, 2=goalkeeper, 0=unknown'),
        DeclareLaunchArgument('send_rate_hz', default_value='10.0',
                               description='UDP send rate in Hz'),
    ]

    sender_node = Node(
        package='robocup_realtime_monitoring',
        executable='robocup_udp_sender',
        name=['robocup_udp_sender_', LaunchConfiguration('robot_id')],
        parameters=[{
            'robot_id': LaunchConfiguration('robot_id'),
            'team_number': LaunchConfiguration('team_number'),
            'udp_broadcast_addr': LaunchConfiguration('udp_broadcast_addr'),
            'role': LaunchConfiguration('role'),
            'send_rate_hz': LaunchConfiguration('send_rate_hz'),
        }],
        output='screen',
    )

    return LaunchDescription(args + [sender_node])
