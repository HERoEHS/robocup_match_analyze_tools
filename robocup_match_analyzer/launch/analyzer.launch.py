from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'web_port', default_value='8096',
            description='Web server port',
        ),
        DeclareLaunchArgument(
            'data_dir',
            default_value='~/blackbox_data',
            description='Directory containing MCAP files',
        ),
        DeclareLaunchArgument(
            'our_team_number', default_value='0',
            description='Our team number (0 = select in UI)',
        ),
        Node(
            package='robocup_match_analyzer',
            executable='strategy_analyzer',
            name='strategy_analyzer',
            output='screen',
            arguments=[
                '--web-port', LaunchConfiguration('web_port'),
                '--data-dir', LaunchConfiguration('data_dir'),
                '--our-team-number', LaunchConfiguration('our_team_number'),
            ],
        ),
    ])
