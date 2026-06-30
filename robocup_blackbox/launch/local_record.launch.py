import os
import tempfile

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

blackbox_dir = get_package_share_directory("robocup_blackbox")
default_config_path = os.path.join(blackbox_dir, "config", "record_profile.yaml")
default_mcap_settings_path = os.path.join(blackbox_dir, "config", "mcap_settings.yaml")


def _read_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _build_mcap_settings(
    compression: str,
    compression_level: str,
    chunk_size: str,
) -> str:
    if not compression or compression.lower() == "none":
        return default_mcap_settings_path

    mcap_cfg = _read_yaml(default_mcap_settings_path)
    mcap_node = mcap_cfg.get("mcap", {})

    fd, mcap_yaml = tempfile.mkstemp(prefix="bb_mcap_", suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        merged = {
            **mcap_node,
            "compression": compression,
            "compression_level": int(compression_level),
            "chunk_size": int(chunk_size),
        }
        yaml.safe_dump({"mcap": merged}, handle, default_flow_style=False, sort_keys=False)
    return mcap_yaml


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() == "true"


def launch_setup(context, *args, **kwargs):
    robot_id = LaunchConfiguration("robot_id").perform(context)
    config_file = LaunchConfiguration("config_file").perform(context)
    enable_live_stream = LaunchConfiguration("enable_live_stream").perform(context)
    compression = LaunchConfiguration("compression").perform(context)
    compression_level = LaunchConfiguration("compression_level").perform(context)
    chunk_size = LaunchConfiguration("chunk_size").perform(context)

    mcap_settings_path = _build_mcap_settings(compression, compression_level, chunk_size)

    return [
        Node(
            package="robocup_blackbox",
            executable="blackbox_writer_node",
            name="blackbox_writer",
            parameters=[{
                "robot_id": robot_id,
                "config_path": config_file,
                "enable_live_stream": _as_bool(enable_live_stream),
                "mcap_settings_path": mcap_settings_path,
            }],
            output="screen",
        )
    ]


def generate_launch_description():
    robot_prefix = os.environ.get("ROBOCUP_GENERATION", "robocup")
    robot_num = os.environ.get("ROBOCUP_ROBOT_ID", "1")
    default_robot_id = f"{robot_prefix}_{robot_num}"

    is_sim = os.environ.get("ROBOCUP_RUNTIME", "sim") == "sim"
    default_live_stream = "true" if is_sim else "false"

    return LaunchDescription([
        DeclareLaunchArgument(
            "robot_id",
            default_value=default_robot_id,
            description="Robot ID (auto-derived from ROBOCUP_GENERATION + ROBOCUP_ROBOT_ID)",
        ),
        DeclareLaunchArgument(
            "config_file",
            default_value=default_config_path,
            description="Path to record profile YAML",
        ),
        DeclareLaunchArgument(
            "enable_live_stream",
            default_value=default_live_stream,
            description="Enable live stream publishing (auto-derived from ROBOCUP_RUNTIME)",
        ),
        DeclareLaunchArgument(
            "compression",
            default_value="none",
            description="mcap chunk compression: none | zstd | lz4",
        ),
        DeclareLaunchArgument(
            "compression_level",
            default_value="3",
            description="Compression level preset (used only when compression != none)",
        ),
        DeclareLaunchArgument(
            "chunk_size",
            default_value="4194304",
            description="MCAP chunk size in bytes (used only when compression != none)",
        ),
        OpaqueFunction(function=launch_setup),
    ])
