"""robocup_realtime_monitoring bringup launch.

Starts the strategy GUI web server (robocup_strategy_gui_web) and,
optionally, one UDP sender per simulated / real robot.

For simulation with robocup_match_2d_simulation, also launch
robocup_udp_sender nodes so the GUI receives robot positions via UDP.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from ament_index_python.packages import get_package_share_directory

_SEP = '-' * 60


def generate_launch_description():
    args = [
        DeclareLaunchArgument(
            'web_port', default_value='8094',
            description='Strategy GUI web port',
        ),
    ]

    banner = LogInfo(msg=[
        '\n', _SEP, '\n',
        'RoboCup Realtime Monitoring: Strategy GUI\n',
        '  http://localhost:', LaunchConfiguration('web_port'), '\n',
        _SEP,
    ])

    strategy_gui_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                get_package_share_directory('robocup_realtime_monitoring'),
                'launch', 'robocup_strategy_gui.launch.py',
            ]),
        ),
        launch_arguments={'web_port': LaunchConfiguration('web_port')}.items(),
    )

    return LaunchDescription(args + [banner, strategy_gui_launch])
