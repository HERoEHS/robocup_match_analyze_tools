import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

blackbox_dir = get_package_share_directory('robocup_blackbox')
default_mcap_settings_path = os.path.join(blackbox_dir, 'config', 'mcap_settings.yaml')
default_config_dir = os.path.join(blackbox_dir, 'config')


def launch_setup(context, *args, **kwargs):
    config_dir = LaunchConfiguration('config_dir').perform(context)
    enable_live_stream = LaunchConfiguration('enable_live_stream').perform(context).lower() == 'true'
    robot_ids = [item.strip() for item in LaunchConfiguration('robot_ids').perform(context).split(',')]

    nodes = []
    for robot_id in robot_ids:
        if not robot_id:
            continue
        config_path = os.path.join(config_dir, f'strategy_gui_sim_robot{robot_id}.yaml')
        nodes.append(Node(
            package='robocup_blackbox',
            executable='blackbox_writer_node',
            name=f'bb_writer_robot{robot_id}',
            parameters=[{
                'robot_id': f'robocup_{robot_id}',
                'config_path': config_path,
                'enable_live_stream': enable_live_stream,
                'mcap_settings_path': default_mcap_settings_path,
            }],
            output='screen',
        ))
    return nodes


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'robot_ids',
            default_value='1,2,3',
            description='Comma-separated list of robot IDs. Launches one recorder per robotN.',
        ),
        DeclareLaunchArgument(
            'config_dir',
            default_value=default_config_dir,
            description='Directory containing strategy_gui_sim_robotN.yaml files.',
        ),
        DeclareLaunchArgument(
            'enable_live_stream',
            default_value='false',
            description='Whether to enable live stream for each recorder.',
        ),
        OpaqueFunction(function=launch_setup),
    ])
