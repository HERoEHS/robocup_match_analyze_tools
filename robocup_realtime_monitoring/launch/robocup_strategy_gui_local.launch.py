from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    web_port_arg = DeclareLaunchArgument(
        'web_port',
        default_value='8094',
        description='robocup_strategy_gui web server port (loopback only)',
    )

    zones_path_arg = DeclareLaunchArgument(
        'zones_path',
        default_value='',
        description='Absolute path override for strategy_zones.yaml. Leave empty to use default launch rules.',
    )

    pkg_share = get_package_share_directory('robocup_realtime_monitoring')
    strategy_gui_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([pkg_share, 'launch', 'robocup_strategy_gui.launch.py'])
        ),
        launch_arguments={
            'web_port': LaunchConfiguration('web_port'),
            'zones_path': LaunchConfiguration('zones_path'),
        }.items(),
    )

    return LaunchDescription([
        web_port_arg,
        zones_path_arg,
        strategy_gui_launch,
    ])
