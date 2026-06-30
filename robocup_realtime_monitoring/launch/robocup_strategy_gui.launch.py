import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    web_port_arg = DeclareLaunchArgument(
        'web_port',
        default_value='8094',
        description='robocup_strategy_gui web server port',
    )

    # Single source-of-truth policy (R-8):
    # The strategy_zones.yaml is always read from / written to the source tree
    # so edits are tracked by git.
    #
    # Priority:
    #   1) ROBOCUP_STRATEGY_ZONES_PATH already exported by the user → use as-is.
    #   2) Auto-detect from this launch file's location.
    #   3) Fall through to zone_store._locate_source_yaml() share fallback.
    user_env = os.environ.get('ROBOCUP_STRATEGY_ZONES_PATH', '').strip()
    if not user_env:
        # Auto-detect: this file lives either in
        #   install/.../share/robocup_realtime_monitoring/launch/   (case 1)
        #   src/robocup_match_analyze_tools/robocup_realtime_monitoring/launch/  (case 2)
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = []
        try:
            # case 1: 5 levels up → workspace root
            ws1 = os.path.abspath(os.path.join(here, '..', '..', '..', '..', '..'))
            candidates.append(os.path.join(
                ws1, 'src', 'robocup_match_analyze_tools', 'robocup_realtime_monitoring',
                'config', 'strategy_zones.yaml',
            ))
        except Exception:
            pass
        try:
            # case 2: 4 levels up → workspace root (src direct run)
            ws2 = os.path.abspath(os.path.join(here, '..', '..', '..', '..'))
            candidates.append(os.path.join(
                ws2, 'src', 'robocup_match_analyze_tools', 'robocup_realtime_monitoring',
                'config', 'strategy_zones.yaml',
            ))
        except Exception:
            pass

        for cand in candidates:
            if os.path.isfile(cand):
                user_env = cand
                print(f"[robocup_strategy_gui.launch] auto-detected yaml: {cand}")
                break
        if not user_env and candidates:
            user_env = candidates[0]
            print(
                f"[robocup_strategy_gui.launch] WARN: yaml not found at inferred path — "
                f"first Save will create it: {user_env}",
            )

    actions = []
    if user_env:
        actions.append(SetEnvironmentVariable(
            name='ROBOCUP_STRATEGY_ZONES_PATH',
            value=user_env,
        ))
        print(f"[robocup_strategy_gui.launch] ROBOCUP_STRATEGY_ZONES_PATH={user_env}")
    else:
        print(
            "[robocup_strategy_gui.launch] WARN: ROBOCUP_STRATEGY_ZONES_PATH not set and "
            "auto-detect failed. zone_store will fall back to share/ path. "
            "Recommended: export ROBOCUP_STRATEGY_ZONES_PATH=<ws>/src/robocup_match_analyze_tools"
            "/robocup_realtime_monitoring/config/strategy_zones.yaml",
        )

    zones_path_arg = DeclareLaunchArgument(
        'zones_path',
        default_value='',
        description=(
            'Absolute path to strategy_zones.yaml (overrides env auto-detection). '
            'Leave empty to use ROBOCUP_STRATEGY_ZONES_PATH or zone_store auto-detect.'
        ),
    )

    udp_bind_addr_arg = DeclareLaunchArgument(
        'udp_bind_addr',
        default_value='127.0.0.1',
        description='UDP receive bind address. Local test: 127.0.0.1 / Network receive: 0.0.0.0',
    )

    gui_node = Node(
        package='robocup_realtime_monitoring',
        executable='robocup_strategy_gui_web',
        name='robocup_strategy_gui',
        output='screen',
        parameters=[{
            'web_port': LaunchConfiguration('web_port'),
            'zones_path': LaunchConfiguration('zones_path'),
            'udp_bind_addr': LaunchConfiguration('udp_bind_addr'),
        }],
    )

    return LaunchDescription(actions + [
        web_port_arg,
        zones_path_arg,
        udp_bind_addr_arg,
        gui_node,
    ])
