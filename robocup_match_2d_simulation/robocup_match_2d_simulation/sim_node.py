"""2D simulator for robocup_realtime_monitoring with built-in control UI.

Features:
- Built-in FastAPI UI for click-selecting robots, opponents, and the ball.
- Manual keyboard control for one selected robot/opponent.
- Direct UDP MessageV2 broadcast for `robocup_realtime_monitoring`.
- Optional legacy ROS topic publishing for the original sender pipeline.
- External RoboCup Game Controller topic integration with READY/SET/PLAYING behavior.
- Direct RoboCup Game Controller UDP receive/send path (replacement for robocup_gamecontroller_client).
"""
from __future__ import annotations

import copy
import math
import random
import socket
import struct
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import rclpy
import uvicorn
import yaml
from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from diagnostic_msgs.msg import KeyValue
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from geometry_msgs.msg import Pose2D, PoseWithCovarianceStamped
from pydantic import BaseModel
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from robocup_msgs.msg import (
    FoundObject,
    FoundObjectArray,
    ObservedRobotArray,
    ProtoBufBallData,
    ProtoBufRobotData,
    RoboCupGameControlRosData,
    RoboCupRobotData,
    RobotRosInfo,
    TeamRosInfo,
)
from starlette.middleware.base import BaseHTTPMiddleware
from std_msgs.msg import Bool, Float64MultiArray, Int16, String

# Byte-for-byte match with _MSG_FMT in udp_listener.py
_MSG_FMT = (
    "<"
    "i" "fff" "fff" "fff" "fff" "i" "ff"
    "fff" "ff" "ff" "ff" "ffff" "ffff" "ff"
    "ifff" "fff" "ifff" "fff"
    "ifff" "ifff" "ifff"
    "i" "???" "fff" "fff" "fff" "fff"
    "B" "B" "ff" "B" "ff" "B" "ff" "B" "ff" "B"
    "B" "B"
    "B" "B" "B" "B" "B" "B" "B" "B" "B" "B" "B" "B"
)
_MSG_STRUCT = struct.Struct(_MSG_FMT)
TEAM_MESSAGE_PORT_BASE = 10000
_STRATEGY_GUI_PACKAGE_CANDIDATES = ("robocup_realtime_monitoring", "robocup_strategy_gui")

_ACTION_NAMES = ["none", "move_to", "turn_to", "kick", "pass", "dribble"]
_ACTION_TO_BT = {
    0: "StopMove",
    1: "MoveTo",
    2: "TurnTo",
    3: "Kick",
    4: "PassTo",
    5: "Dribble",
}
_ALLY_COLORS = ["#4d9fff", "#64d572", "#f7b955", "#bc7cff", "#44d7c6", "#ff8e70", "#d7ecff"]
_OPPONENT_COLORS = ["#ff5c5c", "#ff8b3d", "#ffcd4b"]
_STATE_INITIAL = 0
_STATE_READY = 1
_STATE_SET = 2
_STATE_PLAYING = 3
_STATE_FINISHED = 4
_STATE_STANDBY = 5
_SET_PLAY_NONE = 0
_SET_PLAY_DIRECT_FREE_KICK = 1
_SET_PLAY_INDIRECT_FREE_KICK = 2
_SET_PLAY_PENALTY_KICK = 3
_SET_PLAY_THROW_IN = 4
_SET_PLAY_GOAL_KICK = 5
_SET_PLAY_CORNER_KICK = 6
_KICKING_TEAM_NONE = 255
_PENALTY_NONE = 0
_PENALTY_SIM = 1
_MAX_OPPONENTS = 3
_AUTO_GC_TOPIC_PLAYER_MAX = 5
_GC_STRUCT_HEADER = b"RGme"
_GC_STRUCT_VERSION_V18 = 18
_GC_STRUCT_VERSION_V19 = 19
_GC_STRUCT_VERSION_V20 = 20
_GC_SUPPORTED_STRUCT_VERSIONS = (
    _GC_STRUCT_VERSION_V18,
    _GC_STRUCT_VERSION_V19,
    _GC_STRUCT_VERSION_V20,
)
_GC_DATA_PORT = 3838
_GC_RETURN_PORT = 3939
_GC_RETURN_STRUCT_HEADER = b"RGrt"
_GC_RETURN_STRUCT_VERSION = 4
_GC_HEADER_STRUCT = struct.Struct("<4s10Bhh")
_GC_TEAM_STRUCT = struct.Struct("<6B2H")
_GC_PLAYER_STRUCT_V18 = struct.Struct("<2B")
_GC_PLAYER_STRUCT_V19 = struct.Struct("<4B")
_GC_PLAYER_STRUCT_V20 = struct.Struct("<3B")
_GC_RETURN_STRUCT = struct.Struct("<4s4B3ff2f")
_STATE_NAMES = {
    _STATE_INITIAL: "initial",
    _STATE_READY: "ready",
    _STATE_SET: "set",
    _STATE_PLAYING: "playing",
    _STATE_FINISHED: "finished",
    _STATE_STANDBY: "standby",
}
_SET_PLAY_NAMES = {
    _SET_PLAY_NONE: "none",
    _SET_PLAY_DIRECT_FREE_KICK: "direct_free_kick",
    _SET_PLAY_INDIRECT_FREE_KICK: "indirect_free_kick",
    _SET_PLAY_PENALTY_KICK: "penalty_kick",
    _SET_PLAY_THROW_IN: "throw_in",
    _SET_PLAY_GOAL_KICK: "goal_kick",
    _SET_PLAY_CORNER_KICK: "corner_kick",
}
_GC_PACKET_SIZES = {
    _GC_STRUCT_VERSION_V18: _GC_HEADER_STRUCT.size + (2 * _GC_TEAM_STRUCT.size) + (40 * _GC_PLAYER_STRUCT_V18.size),
    _GC_STRUCT_VERSION_V19: _GC_HEADER_STRUCT.size + (2 * _GC_TEAM_STRUCT.size) + (40 * _GC_PLAYER_STRUCT_V19.size),
    _GC_STRUCT_VERSION_V20: _GC_HEADER_STRUCT.size + (2 * _GC_TEAM_STRUCT.size) + (40 * _GC_PLAYER_STRUCT_V20.size),
}
_DEFAULT_BORDER_STRIP = 1.0
_DEFAULT_CENTER_CIRCLE_RADIUS = 1.5
_DEFAULT_CENTER_CIRCLE_MARGIN = 0.3
_DEFAULT_GOAL_AREA_DEPTH = 1.0
_DEFAULT_GOAL_AREA_WIDTH = 4.0
_DEFAULT_TOUCHLINE_WAIT_MARGIN = 0.3
_DEFAULT_GOALKEEPER_SET_MARGIN = 0.45
_DEFAULT_KICK_CONTACT_RADIUS = 0.58
_DEFAULT_KICK_PUSH_DISTANCE = 0.22
_DEFAULT_KICK_SPEED = 3.8
_DEFAULT_KICK_ACTIVE_SEC = 0.6
_DEFAULT_BALL_WALL_RESTITUTION = 0.8
_DEFAULT_KICK_CONTROL_SPEED_MAX = 0.8
_DEFAULT_RECIPROCAL_KICK_COOLDOWN = 2.0
_DEFAULT_RECIPROCAL_KICK_RELEASE_DISTANCE = 0.9
_DEFAULT_KICK_DIRECTION_SAMPLE_COUNT = 8
_DEFAULT_KICK_DIRECTION_JITTER_RAD = math.radians(70.0)
_DEFAULT_BALL_WALL_ESCAPE_MARGIN = 0.45
_DEFAULT_BALL_WALL_ESCAPE_DISTANCE = 1.1
_DEFAULT_ROBOT_OUTSIDE_FIELD_MARGIN = 0.8
_DEFAULT_WAIT_BALL_MOVE_THRESHOLD = 0.4
_DEFAULT_WAIT_BALL_MOVE_TIMEOUT_SEC = 3.0
_DEFAULT_CHASER_CLUSTER_EPS = 0.5
_DEFAULT_TEAM_POSSESSION_MARGIN = 0.25
_DEFAULT_SUPPORT_FORWARD = 0.8
_DEFAULT_SUPPORT_LATERAL = 2.0
_DEFAULT_SUPPORT_FIELD_MARGIN = 0.5
_DEFAULT_GUARD_BEHIND = 2.5
_DEFAULT_DRIBBLE_HOLD_DISTANCE = 0.28
_DEFAULT_DRIBBLE_CAPTURE_RADIUS = 0.42
_DEFAULT_KEEPER_RUSH_BALL_DIST = 1.5
_DEFAULT_DRIBBLE_FRONT_CONE_HALF_DEG = 55.0
_DEFAULT_DRIBBLE_STEER_ENTER_DEG = 20.0
_DEFAULT_DRIBBLE_HEADING_ONLY_DEG = 38.0
_DEFAULT_DRIBBLE_MAX_CONTINUOUS_SEC = 2.2
_DEFAULT_KICKOFF_FIRST_TOUCH_TARGET = 1.7
_DEFAULT_KICKOFF_SECOND_TOUCH_TARGET = 7.2
_DEFAULT_KICKOFF_HANDOFF_PROGRESS = 3.2
_DEFAULT_KICKOFF_PLAN_WINDOW_SEC = 6.0
_DEFAULT_ROBOT_BODY_RADIUS = 0.35
_DEFAULT_ROBOT_CONTACT_BUFFER = 0.14
_DEFAULT_CONTACT_RESOLVE_PASSES = 4
_DEFAULT_CONTACT_FALL_PROB = 0.0015


@dataclass
class AgentState:
    player_id: int
    team: str
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0
    orbit_cx: float = 0.0
    orbit_cy: float = 0.0
    orbit_radius: float = 2.0
    orbit_angle: float = 0.0
    orbit_speed: float = 0.3
    target_x: float = 0.0
    target_y: float = 0.0
    override_x: Optional[float] = None
    override_y: Optional[float] = None
    override_theta: Optional[float] = None
    override_expires: float = 0.0
    role: int = 1
    eval_mc: float = 0.85
    action: int = 1
    penalty: bool = False
    kick_latched: bool = False
    dribble_since: float = 0.0
    wander_target_x: float = 0.0
    wander_target_y: float = 0.0
    wander_next: float = 0.0
    vel_x: float = 0.0
    vel_y: float = 0.0
    fallen: bool = False
    fallen_at: float = 0.0


@dataclass
class BallState:
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.4
    vy: float = 0.3
    override_x: Optional[float] = None
    override_y: Optional[float] = None
    override_expires: float = 0.0
    kick_until: float = 0.0
    kick_cooldown_until: float = 0.0
    last_kick_at: float = 0.0
    last_kick_origin_x: float = 0.0
    last_kick_origin_y: float = 0.0
    last_kicker_team: str = ""
    bypass_block_until: float = 0.0
    bypass_block_team: str = ""


class PoseBody(BaseModel):
    x: float
    y: float
    theta: float = 0.0


class BallBody(BaseModel):
    x: float
    y: float


class ControlBody(BaseModel):
    action: str
    value: float = 1.0


class ManualSelectBody(BaseModel):
    team: str
    id: int
    enabled: bool = False


class ManualInputBody(BaseModel):
    vx: float = 0.0
    vy: float = 0.0
    omega: float = 0.0


class LegacyRobotIdBody(BaseModel):
    robot_id: int


class LegacyRobotIdsBody(BaseModel):
    robot_ids: list[int]


class NoiseBody(BaseModel):
    enabled: bool | None = None
    show_in_gui: bool | None = None
    self_pos: float | None = None
    self_angle: float | None = None
    ball: float | None = None
    other_robot: float | None = None


class FallBody(BaseModel):
    fall_prob: float | None = None
    recovery_sec: float | None = None


class FovBody(BaseModel):
    angle_deg: float | None = None
    range_m: float | None = None


@dataclass(frozen=True)
class CommanderSetPoints:
    goalkeeper: tuple[float, float, float] = (-5.5, 0.0, 0.0)
    kickoff_primary: tuple[float, float, float] = (-1.0, 0.0, 0.0)
    defense_primary: tuple[float, float, float] = (-2.0, 0.0, 0.0)
    kickoff_secondary: tuple[float, float, float] = (-1.5, 2.0, 0.0)
    defense_secondary: tuple[float, float, float] = (-2.5, 2.0, 0.0)


@dataclass(frozen=True)
class CommanderMotionConfig:
    arrive_threshold: float = 0.25
    ball_capture_threshold: float = 0.22
    defense_offset: float = 1.8
    pass_offset: float = 4.0
    dribble_offset: float = 0.3
    orbital_radius: float = 0.35
    goal_half_width: float = 1.1
    ball_approach_offset: float = 0.22
    center_circle_radius: float = 1.5
    center_circle_margin: float = 0.3
    block_goal_offset: float = 1.5
    keeper_rush_offset: float = 3.5
    block_deadband: float = 0.1
    dribble_quit_threshold: float = 0.3
    pass_max_distance: float = 4.0
    goal_aim_min_angle_deg: float = 10.0


@dataclass(frozen=True)
class PlayCommand:
    target_x: float
    target_y: float
    target_theta: float
    max_speed: float
    forced_action: Optional[int] = None
    prefer_heading: bool = False
    heading_only_angle_deg: float = 180.0


@dataclass
class ExternalGcState:
    msg: RoboCupGameControlRosData
    source_topic: str
    received_at: float
    team_index: int
    opponent_team_index: int


class StrategyGuiSim(Node):
    def __init__(self) -> None:
        super().__init__("robocup_match_2d_simulation")

        self.declare_parameter("num_robots", 3)
        self.declare_parameter("num_opponents", 3)
        self.declare_parameter("team_number", 25)
        self.declare_parameter("opponent_team_number", 26)
        self.declare_parameter("inet_address", "127.0.0.1")
        self.declare_parameter("send_interval_ms", 100)
        self.declare_parameter("field_length", 14.0)
        self.declare_parameter("field_width", 9.0)
        self.declare_parameter("override_duration_sec", 3.0)
        self.declare_parameter("ui_port", 8095)
        self.declare_parameter("publish_udp", True)
        self.declare_parameter("publish_legacy_topics", True)
        self.declare_parameter("legacy_topic_robot_id", 1)
        self.declare_parameter("legacy_topic_robot_ids", "")
        self.declare_parameter("use_external_gc", True)
        self.declare_parameter("external_gc_timeout_sec", 1.0)
        self.declare_parameter("external_gc_topics", "")
        self.declare_parameter("require_gc_for_motion", True)
        self.declare_parameter("direct_gc_required_for_motion", False)
        self.declare_parameter("receive_gc_direct_udp", True)
        self.declare_parameter("publish_gc_ros_topics", True)
        self.declare_parameter("game_controller_address", "")
        self.declare_parameter("game_controller_data_port", _GC_DATA_PORT)
        self.declare_parameter("game_controller_return_port", _GC_RETURN_PORT)
        self.declare_parameter("gc_udp_poll_interval_ms", 50)
        self.declare_parameter("gc_allowed_source_ip", "127.0.0.1")

        num_robots = max(1, min(7, int(self.get_parameter("num_robots").value)))
        num_opponents = max(0, min(_MAX_OPPONENTS, int(self.get_parameter("num_opponents").value)))
        self._team_number = int(self.get_parameter("team_number").value)
        self._opponent_team_number = int(self.get_parameter("opponent_team_number").value)
        if self._opponent_team_number <= 0 or self._opponent_team_number == self._team_number:
            self._opponent_team_number = self._team_number + 1 if self._team_number < 255 else max(1, self._team_number - 1)
        self._inet_addr = str(self.get_parameter("inet_address").value)
        interval_ms = int(self.get_parameter("send_interval_ms").value)
        self._field_l = float(self.get_parameter("field_length").value)
        self._field_w = float(self.get_parameter("field_width").value)
        self._override_duration = float(self.get_parameter("override_duration_sec").value)
        self.ui_port = int(self.get_parameter("ui_port").value)
        self._publish_udp = bool(self.get_parameter("publish_udp").value)
        self._publish_legacy_topics = bool(self.get_parameter("publish_legacy_topics").value)
        self._external_gc_enabled = bool(self.get_parameter("use_external_gc").value)
        self._external_gc_timeout = max(0.1, float(self.get_parameter("external_gc_timeout_sec").value))
        self._require_gc_for_motion = bool(self.get_parameter("require_gc_for_motion").value)
        self._direct_gc_required_for_motion = bool(self.get_parameter("direct_gc_required_for_motion").value)
        self._receive_gc_direct_udp = bool(self.get_parameter("receive_gc_direct_udp").value)
        self._publish_gc_ros_topics = bool(self.get_parameter("publish_gc_ros_topics").value)
        self._gc_send_override_ip = str(self.get_parameter("game_controller_address").value).strip()
        self._gc_data_port = int(self.get_parameter("game_controller_data_port").value)
        self._gc_return_port = int(self.get_parameter("game_controller_return_port").value)
        gc_poll_ms = int(self.get_parameter("gc_udp_poll_interval_ms").value)
        self._gc_udp_poll_interval = max(0.01, gc_poll_ms / 1000.0)
        self._gc_allowed_source_ip = str(self.get_parameter("gc_allowed_source_ip").value).strip()

        self._num_robots = num_robots
        self._num_opponents = num_opponents
        legacy_ids_csv = str(self.get_parameter("legacy_topic_robot_ids").value)
        self._legacy_topic_robot_ids = self._parse_legacy_robot_ids(legacy_ids_csv, num_robots)
        if not self._legacy_topic_robot_ids:
            _init_id = max(1, min(num_robots, int(self.get_parameter("legacy_topic_robot_id").value)))
            self._legacy_topic_robot_ids = [_init_id]
        self._external_gc_topics = self._resolve_external_gc_topics(str(self.get_parameter("external_gc_topics").value))
        self._port = TEAM_MESSAGE_PORT_BASE + self._team_number
        self._lock = threading.Lock()
        self._paused = False
        self._speed_mult = 1.0

        self._noise_enabled = True
        self._noise_show_in_gui = True
        self._noise_self_pos = 0.01
        self._noise_self_angle = 0.01
        self._noise_ball = 0.01
        self._noise_other_robot = 0.01

        self._robot_body_radius = _DEFAULT_ROBOT_BODY_RADIUS
        self._robot_contact_distance = (self._robot_body_radius * 2.0) + _DEFAULT_ROBOT_CONTACT_BUFFER
        self._fall_prob: float = _DEFAULT_CONTACT_FALL_PROB
        self._fall_recovery_sec: float = 15.0
        self._fov_angle_deg: float = 120.0
        self._fov_range_m: float = 8.0

        self._manual_enabled = False
        self._manual_target_team = "none"
        self._manual_target_id = 0
        self._manual_vx = 0.0
        self._manual_vy = 0.0
        self._manual_omega = 0.0
        self._gc_packet_number = 0
        self._last_external_gc_source = ""
        self._set_points = self._load_commander_set_points()
        self._motion_cfg = self._load_commander_motion_config()
        self._load_rule_field_geometry()
        self._role_by_player = self._load_simulation_roles()
        self._external_gc: ExternalGcState | None = None
        self._kickoff_release_pending = False
        self._kickoff_release_started_at = 0.0
        self._kickoff_release_origin_x = 0.0
        self._kickoff_release_origin_y = 0.0
        self._kickoff_release_origin_fixed = False
        self._kickoff_plan_started_at = 0.0
        self._kickoff_plan_team_number = 0
        self._kickoff_plan_completed = False
        self._gc_udp_sock: socket.socket | None = None
        self._gc_udp_connected_once = False
        self._gc_udp_last_sender_ip = ""
        self._gc_udp_last_received_at = 0.0
        self._owned_gc_topics: set[str] = set()
        self._ignore_owned_gc_topics_until = 0.0
        self._recent_direct_gc_packets: dict[int, float] = {}

        self._robots = self._init_agents(team="ally", count=self._num_robots)
        self._opponents = self._init_agents(team="opponent", count=self._num_opponents)

        # Per-robot startup time offset (0–500 ms) to simulate real robots
        # starting blackbox recording at slightly different times.
        self._robot_startup_offset_ns: dict[int, int] = {
            pid: random.randint(0, 500_000_000)
            for pid in range(1, self._num_robots + 1)
        }
        self._ball = BallState(
            x=0.0,
            y=0.0,
            vx=0.0,
            vy=0.0,
        )
        self._init_ball = BallState(x=self._ball.x, y=self._ball.y, vx=self._ball.vx, vy=self._ball.vy)

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        self._subs = []
        for robot in self._robots:
            self._subs.append(
                self.create_subscription(
                    Pose2D,
                    f"/sim/robot{robot.player_id}/pose",
                    lambda msg, pid=robot.player_id: self.override_agent("ally", pid, msg.x, msg.y, msg.theta),
                    10,
                ),
            )
        for opponent in self._opponents:
            self._subs.append(
                self.create_subscription(
                    Pose2D,
                    f"/sim/opponent{opponent.player_id}/pose",
                    lambda msg, pid=opponent.player_id: self.override_agent("opponent", pid, msg.x, msg.y, msg.theta),
                    10,
                ),
            )
        self._subs.append(self.create_subscription(Pose2D, "/sim/ball/pose", self._cb_ball_pose, 10))
        self._subs.extend(self._create_external_gc_subscriptions())

        if self._publish_legacy_topics:
            self._pubs = self._create_legacy_publishers()
            self._pubs_per_robot: dict[int, dict] = {
                pid: self._create_per_robot_publishers(pid)
                for pid in range(1, num_robots + 1)
            }
        else:
            self._pubs = {}
            self._pubs_per_robot = {}
        self._gc_direct_pubs = self._create_gc_direct_publishers() if self._publish_gc_ros_topics else {}

        self._last_tick = time.monotonic()
        self._timer = self.create_timer(interval_ms / 1000.0, self._tick)
        self._gc_udp_timer = self._init_direct_gc_udp()

        self.get_logger().info(
            "Sim: allies=%d opponents=%d udp=%s legacy_topics=%s -> %s:%d (%dms, %dB)"
            % (
                self._num_robots,
                self._num_opponents,
                self._publish_udp,
                self._publish_legacy_topics,
                self._inet_addr,
                self._port,
                interval_ms,
                _MSG_STRUCT.size,
            ),
        )
        if self._external_gc_enabled:
            self.get_logger().info(
                "External GC: timeout=%.2fs topics=%s"
                % (self._external_gc_timeout, ", ".join(self._external_gc_topics)),
            )
        if self._receive_gc_direct_udp:
            override = self._gc_send_override_ip or "sender address"
            self.get_logger().info(
                "Direct GC UDP: receive=0.0.0.0:%d return=%s:%d poll=%.0fms"
                % (self._gc_data_port, override, self._gc_return_port, self._gc_udp_poll_interval * 1000.0),
            )

    def _create_legacy_publishers(self) -> dict[str, object]:
        return {
            "local_pose": self.create_publisher(Pose2D, "/robocup/localization/pose", 10),
            "destination": self.create_publisher(Pose2D, "/robocup/destination", 10),
            "pass_target": self.create_publisher(Pose2D, "/robocup/pass_target", 10),
            "detected_objects": self.create_publisher(FoundObjectArray, "/robocup/detected_objects", 10),
            "pass_sequence": self.create_publisher(Int16, "/robocup/pass_sequence", 10),
            "bt_node": self.create_publisher(String, "/robocup/current_bt_node", 10),
            "game": self.create_publisher(RoboCupGameControlRosData, "/robocup/game_control_data", 10),
            "lifted": self.create_publisher(Bool, "/robocup/lifted", 10),
            "result_cov": self.create_publisher(PoseWithCovarianceStamped, "/robocup/localization/result_with_cov", 10),
            "fused_enemies": self.create_publisher(ObservedRobotArray, "/robocup/cooperative_perception/enemies", 10),
            "udp_data": self.create_publisher(RoboCupRobotData, "/robocup/udp/data", 10),
            "rl_vel_cmd": self.create_publisher(Float64MultiArray, "/robocup/rl_vel_cmd", 10),
        }

    def _create_per_robot_publishers(self, robot_id: int) -> dict[str, object]:
        p = f"/robocup_{robot_id}"
        return {
            "local_pose": self.create_publisher(Pose2D, f"{p}/localization/pose", 10),
            "destination": self.create_publisher(Pose2D, f"{p}/destination", 10),
            "pass_target": self.create_publisher(Pose2D, f"{p}/pass_target", 10),
            "detected_objects": self.create_publisher(FoundObjectArray, f"{p}/detected_objects", 10),
            "pass_sequence": self.create_publisher(Int16, f"{p}/pass_sequence", 10),
            "bt_node": self.create_publisher(String, f"{p}/current_bt_node", 10),
            "game": self.create_publisher(RoboCupGameControlRosData, f"{p}/game_control_data", 10),
            "lifted": self.create_publisher(Bool, f"{p}/lifted", 10),
            "result_cov": self.create_publisher(PoseWithCovarianceStamped, f"{p}/localization/result_with_cov", 10),
            "fused_enemies": self.create_publisher(ObservedRobotArray, f"{p}/cooperative_perception/enemies", 10),
            "udp_data": self.create_publisher(RoboCupRobotData, f"{p}/udp/data", 10),
            "rl_vel_cmd": self.create_publisher(Float64MultiArray, f"{p}/rl_vel_cmd", 10),
        }

    def _create_gc_direct_publishers(self) -> dict[str, object]:
        self._owned_gc_topics = {"/robocup/game_control_data"}
        per_robot = {
            player_id: self.create_publisher(
                RoboCupGameControlRosData,
                f"/robocup_{player_id}/game_control_data",
                10,
            )
            for player_id in range(1, self._num_robots + 1)
        }
        self._owned_gc_topics.update(per_robot_topic for per_robot_topic in [
            f"/robocup_{player_id}/game_control_data"
            for player_id in range(1, self._num_robots + 1)
        ])
        return {
            "single": self.create_publisher(
                RoboCupGameControlRosData,
                "/robocup/game_control_data",
                10,
            ),
            "per_robot": per_robot,
        }

    def _init_agents(self, team: str, count: int) -> list[AgentState]:
        agents: list[AgentState] = []
        if count <= 0:
            return agents
        # ally=right(+x) side, opponent=left(−x) side (default no-GC placement)
        half_l = self._field_l / 2
        half_w = self._field_w / 2
        angle_offset = 0.4 if team == "ally" else math.pi + 0.2
        speed_sign = 1.0 if team == "ally" else -1.0
        # initial wander centers: spread robots across the field
        _wander_cx_pool_ally = [half_l * 0.7, -half_l * 0.2, half_l * 0.15, -half_l * 0.6, half_l * 0.45, -half_l * 0.05, half_l * 0.8]
        _wander_cx_pool_opp  = [-half_l * 0.7, half_l * 0.2, -half_l * 0.15, half_l * 0.6, -half_l * 0.45, half_l * 0.05, -half_l * 0.8]
        _wander_cy_pool = [0.0, half_w * 0.55, -half_w * 0.55, half_w * 0.8, -half_w * 0.8, half_w * 0.3, -half_w * 0.3]
        cx_pool = _wander_cx_pool_ally if team == "ally" else _wander_cx_pool_opp
        for i in range(count):
            player_id = i + 1
            radius = 2.2 + i * 0.7
            angle = angle_offset + i * 0.7
            center_x = cx_pool[i % len(cx_pool)]
            center_y = _wander_cy_pool[i % len(_wander_cy_pool)]
            role = self._role_by_player.get(player_id, 1)
            x, y, theta = self._get_waiting_pose(team, player_id, role, count)
            agents.append(
                AgentState(
                    player_id=player_id,
                    team=team,
                    x=x,
                    y=y,
                    theta=self._wrap_angle(theta),
                    orbit_cx=center_x,
                    orbit_cy=center_y,
                    orbit_radius=radius,
                    orbit_angle=angle,
                    orbit_speed=speed_sign * (0.50 + i * 0.08),
                    target_x=x,
                    target_y=y,
                    role=role,
                    eval_mc=round(random.uniform(0.78, 0.96), 2),
                    action=1,
                    wander_target_x=center_x,
                    wander_target_y=center_y,
                    wander_next=time.monotonic() + i * 1.5 + random.uniform(0.5, 2.0),
                ),
            )
        return agents

    def _sim_config_path(self) -> Path:
        try:
            share_dir = Path(get_package_share_directory("robocup_match_2d_simulation"))
        except PackageNotFoundError:
            share_dir = Path(__file__).parent.parent / "config"
        return share_dir / "config" / "sim_config.yaml"

    def _load_sim_config(self) -> dict:
        config_path = self._sim_config_path()
        if not config_path.exists():
            self.get_logger().warn(f"sim_config.yaml not found at {config_path}. using built-in defaults.")
            return {}
        try:
            with config_path.open("r", encoding="utf-8") as file:
                return yaml.safe_load(file) or {}
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"Failed to load sim_config.yaml: {exc}")
            return {}

    def _load_commander_set_points(self) -> CommanderSetPoints:
        defaults = CommanderSetPoints()
        cfg = self._load_sim_config().get("set_points", {})
        if not cfg:
            return defaults

        def read_pose(name: str, fallback: tuple[float, float, float]) -> tuple[float, float, float]:
            values = cfg.get(name)
            if not isinstance(values, list) or len(values) < 2:
                return fallback
            theta = float(values[2]) if len(values) >= 3 else 0.0
            return (float(values[0]), float(values[1]), theta)

        return CommanderSetPoints(
            goalkeeper=read_pose("goalkeeper", defaults.goalkeeper),
            kickoff_primary=read_pose("kickoff_primary", defaults.kickoff_primary),
            defense_primary=read_pose("defense_primary", defaults.defense_primary),
            kickoff_secondary=read_pose("kickoff_secondary", defaults.kickoff_secondary),
            defense_secondary=read_pose("defense_secondary", defaults.defense_secondary),
        )

    def _load_commander_motion_config(self) -> CommanderMotionConfig:
        defaults = CommanderMotionConfig()
        cfg = self._load_sim_config().get("motion", {})
        if not cfg:
            return defaults

        def read_float(name: str, fallback: float) -> float:
            try:
                return float(cfg.get(name, fallback))
            except (TypeError, ValueError):
                return fallback

        return CommanderMotionConfig(
            arrive_threshold=read_float("arrive_threshold", defaults.arrive_threshold),
            ball_capture_threshold=read_float("ball_capture_threshold", defaults.ball_capture_threshold),
            defense_offset=read_float("defense_offset", defaults.defense_offset),
            pass_offset=read_float("pass_offset", defaults.pass_offset),
            dribble_offset=read_float("dribble_offset", defaults.dribble_offset),
            orbital_radius=read_float("orbital_radius", defaults.orbital_radius),
            goal_half_width=read_float("goal_half_width", defaults.goal_half_width),
            ball_approach_offset=read_float("ball_approach_offset", defaults.ball_approach_offset),
            center_circle_radius=read_float("center_circle_radius", defaults.center_circle_radius),
            center_circle_margin=read_float("center_circle_margin", defaults.center_circle_margin),
            block_goal_offset=read_float("block_goal_offset", defaults.block_goal_offset),
            keeper_rush_offset=read_float("keeper_rush_offset", defaults.keeper_rush_offset),
            block_deadband=read_float("block_deadband", defaults.block_deadband),
            dribble_quit_threshold=read_float("dribble_quit_threshold", defaults.dribble_quit_threshold),
            pass_max_distance=read_float("pass_max_distance", defaults.pass_max_distance),
            goal_aim_min_angle_deg=read_float("goal_aim_min_angle_deg", defaults.goal_aim_min_angle_deg),
        )

    def _load_rule_field_geometry(self) -> None:
        self._border_strip = _DEFAULT_BORDER_STRIP
        self._center_circle_radius = self._motion_cfg.center_circle_radius
        self._center_circle_margin = self._motion_cfg.center_circle_margin
        self._goal_area_depth = _DEFAULT_GOAL_AREA_DEPTH
        self._goal_area_width = _DEFAULT_GOAL_AREA_WIDTH

        gui_share_dir: Optional[Path] = None
        gui_package_name: Optional[str] = None
        lookup_errors: list[str] = []
        for package_name in _STRATEGY_GUI_PACKAGE_CANDIDATES:
            try:
                gui_share_dir = Path(get_package_share_directory(package_name))
                gui_package_name = package_name
                break
            except Exception as exc:  # noqa: BLE001
                lookup_errors.append(f"{package_name}: {exc}")

        if gui_share_dir is None:
            self.get_logger().warn(
                "Failed to locate strategy GUI config package: " + " | ".join(lookup_errors)
            )
        else:
            try:
                zones_path = gui_share_dir / "config" / "strategy_zones.yaml"
                if zones_path.exists():
                    with zones_path.open("r", encoding="utf-8") as file:
                        config = yaml.safe_load(file) or {}
                    field = config.get("field", {})
                    goal_area = field.get("goal_area", {})
                    self._border_strip = float(field.get("border_strip_m", self._border_strip))
                    self._center_circle_radius = float(field.get("center_circle_r_m", self._center_circle_radius))
                    self._goal_area_depth = float(goal_area.get("depth_m", self._goal_area_depth))
                    self._goal_area_width = float(goal_area.get("width_m", self._goal_area_width))
            except Exception as exc:  # noqa: BLE001
                self.get_logger().warn(
                    f"Failed to load field rule geometry from {gui_package_name} config: {exc}"
                )

        motion = self._load_sim_config().get("motion", {})
        if "center_circle_radius" in motion:
            self._center_circle_radius = float(motion["center_circle_radius"])
        if "center_circle_margin" in motion:
            self._center_circle_margin = float(motion["center_circle_margin"])

    def _load_simulation_roles(self) -> dict[int, int]:
        default_roles = {1: 2}
        players = self._load_sim_config().get("simulation_roles")
        if not isinstance(players, list):
            return default_roles
        loaded_roles = {}
        for player in players:
            if not isinstance(player, dict):
                continue
            player_number = int(player.get("player_number", 0))
            role = int(player.get("role", 1))
            if player_number > 0:
                loaded_roles[player_number] = 2 if role == 2 else 1
        return loaded_roles if loaded_roles else default_roles

    def _resolve_external_gc_topics(self, csv_text: str) -> list[str]:
        topics: list[str] = []
        if csv_text.strip():
            for raw in csv_text.split(","):
                topic = raw.strip()
                if topic:
                    topics.append(topic)
        else:
            topics.append("/robocup/game_control_data")
            max_player_id = max(self._num_robots, _AUTO_GC_TOPIC_PLAYER_MAX)
            for player_id in range(1, max_player_id + 1):
                topics.append(f"/robocup_{player_id}/game_control_data")
        unique: list[str] = []
        for topic in topics:
            if topic not in unique:
                unique.append(topic)
        return unique

    def _create_external_gc_subscriptions(self) -> list[object]:
        if not self._external_gc_enabled:
            return []
        subs = []
        for topic in self._external_gc_topics:
            subs.append(
                self.create_subscription(
                    RoboCupGameControlRosData,
                    topic,
                    lambda msg, subscribed_topic=topic: self._cb_external_gc(msg, subscribed_topic),
                    10,
                ),
            )
        return subs

    def _init_direct_gc_udp(self):
        if not self._receive_gc_direct_udp:
            return None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            reuse = 1
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, reuse)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, reuse)
                except OSError:
                    pass
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("0.0.0.0", self._gc_data_port))
            sock.setblocking(False)
        except OSError as exc:
            self.get_logger().error(f"Failed to bind direct GC UDP socket on {self._gc_data_port}: {exc}")
            self._receive_gc_direct_udp = False
            return None
        self._gc_udp_sock = sock
        return self.create_timer(self._gc_udp_poll_interval, self._poll_gc_udp)

    def _poll_gc_udp(self) -> None:
        sock = self._gc_udp_sock
        if sock is None:
            return

        while True:
            try:
                packet, addr = sock.recvfrom(2048)
            except BlockingIOError:
                break
            except OSError as exc:
                self.get_logger().warn(f"Direct GC UDP recv failed: {exc}", throttle_duration_sec=5.0)
                break

            if self._gc_allowed_source_ip and addr[0] != self._gc_allowed_source_ip:
                self.get_logger().debug(
                    f"GC UDP from {addr[0]} ignored (allowed: {self._gc_allowed_source_ip})",
                )
                continue
            msg = self._decode_gc_udp_packet(packet)
            if msg is None:
                continue
            self._gc_udp_connected_once = True
            self._gc_udp_last_sender_ip = addr[0]
            self._gc_udp_last_received_at = time.monotonic()
            self._ignore_owned_gc_topics_until = self._gc_udp_last_received_at + max(0.5, self._external_gc_timeout)
            self._remember_direct_gc_packet(int(msg.packet_number))
            self._accept_external_gc(msg, f"udp://{addr[0]}:{addr[1]}")
            if self._publish_gc_ros_topics:
                self._publish_direct_gc_topics(msg)

        if self._gc_udp_connected_once:
            self._send_gc_return_packets()

    def _direct_gc_udp_active(self, now: float | None = None) -> bool:
        if not self._receive_gc_direct_udp or not self._gc_udp_connected_once:
            return False
        if now is None:
            now = time.monotonic()
        return (now - self._gc_udp_last_received_at) <= self._external_gc_timeout

    def _remember_direct_gc_packet(self, packet_number: int) -> None:
        now = time.monotonic()
        expiry = now + max(0.5, self._external_gc_timeout)
        self._recent_direct_gc_packets[packet_number] = expiry
        expired = [number for number, until in self._recent_direct_gc_packets.items() if until < now]
        for number in expired:
            self._recent_direct_gc_packets.pop(number, None)

    def _is_recent_direct_gc_packet(self, packet_number: int) -> bool:
        now = time.monotonic()
        expiry = self._recent_direct_gc_packets.get(packet_number)
        if expiry is None:
            return False
        if expiry < now:
            self._recent_direct_gc_packets.pop(packet_number, None)
            return False
        return True

    def _decode_gc_udp_packet(self, packet: bytes) -> RoboCupGameControlRosData | None:
        if len(packet) < _GC_HEADER_STRUCT.size:
            return None
        try:
            unpacked = _GC_HEADER_STRUCT.unpack_from(packet, 0)
        except struct.error:
            return None

        header = unpacked[0]
        if header != _GC_STRUCT_HEADER:
            return None
        version = int(unpacked[1])
        if version not in _GC_SUPPORTED_STRUCT_VERSIONS:
            self.get_logger().warn(
                f"Ignoring GC UDP packet with unsupported version={version} supported={_GC_SUPPORTED_STRUCT_VERSIONS}",
                throttle_duration_sec=5.0,
            )
            return None

        required_size = _GC_PACKET_SIZES[version]
        if len(packet) < required_size:
            self.get_logger().warn(
                f"Ignoring truncated GC UDP packet version={version} size={len(packet)} expected_at_least={required_size}",
                throttle_duration_sec=5.0,
            )
            return None

        msg = RoboCupGameControlRosData()
        msg.header = header.decode("ascii", errors="ignore")
        msg.version = version
        msg.packet_number = int(unpacked[2])
        msg.players_per_team = int(unpacked[3])
        if version == _GC_STRUCT_VERSION_V18:
            msg.competition_type = int(unpacked[5])
            msg.stopped = 0
            msg.game_phase = int(unpacked[6])
            msg.state = int(unpacked[7])
            msg.set_play = self._translate_gc_v18_set_play(int(unpacked[8]))
            msg.first_half = int(unpacked[9])
            msg.kicking_team = int(unpacked[10])
            player_struct = _GC_PLAYER_STRUCT_V18
        elif version == _GC_STRUCT_VERSION_V19:
            msg.competition_type = int(unpacked[4])
            msg.stopped = int(unpacked[5])
            msg.game_phase = int(unpacked[6])
            msg.state = int(unpacked[7])
            msg.set_play = int(unpacked[8])
            msg.first_half = int(unpacked[9])
            msg.kicking_team = int(unpacked[10])
            player_struct = _GC_PLAYER_STRUCT_V19
        else:
            msg.competition_type = int(unpacked[4])
            msg.stopped = int(unpacked[5])
            msg.game_phase = int(unpacked[6])
            msg.state = int(unpacked[7])
            msg.set_play = int(unpacked[8])
            msg.first_half = int(unpacked[9])
            msg.kicking_team = int(unpacked[10])
            player_struct = _GC_PLAYER_STRUCT_V20
        msg.secs_remaining = int(unpacked[11])
        msg.secondary_time = int(unpacked[12])

        offset = _GC_HEADER_STRUCT.size
        for team_index in range(2):
            try:
                team_values = _GC_TEAM_STRUCT.unpack_from(packet, offset)
            except struct.error:
                return None
            offset += _GC_TEAM_STRUCT.size

            team_msg = msg.teams[team_index]
            team_msg.team_number = int(team_values[0])
            team_msg.field_player_colour = int(team_values[1])
            team_msg.goalkeeper_colour = int(team_values[2])
            team_msg.goalkeeper = int(team_values[3])
            team_msg.score = int(team_values[4])
            team_msg.penalty_shot = int(team_values[5])
            team_msg.single_shots = int(team_values[6])
            team_msg.message_budget = int(team_values[7])

            for player_index in range(20):
                try:
                    player_values = player_struct.unpack_from(packet, offset)
                except struct.error:
                    return None
                offset += player_struct.size
                player_msg = team_msg.players[player_index]
                player_msg.penalty = int(player_values[0])
                player_msg.secs_till_unpenalised = int(player_values[1])
                if version == _GC_STRUCT_VERSION_V19:
                    player_msg.cautions = int(player_values[3])
                elif version == _GC_STRUCT_VERSION_V20:
                    player_msg.cautions = int(player_values[2])
                else:
                    player_msg.cautions = 0

        msg.secondary_state = self._synthesize_secondary_state(msg)
        msg.secondary_state_info = [int(msg.kicking_team), int(msg.state), 0, 0]
        msg.kick_off_team = int(msg.kicking_team)
        msg.team_index = 0
        msg.robot_index = 0
        return msg

    def _translate_gc_v18_set_play(self, set_play: int) -> int:
        return {
            0: _SET_PLAY_NONE,
            1: _SET_PLAY_GOAL_KICK,
            2: _SET_PLAY_DIRECT_FREE_KICK,
            3: _SET_PLAY_CORNER_KICK,
            4: _SET_PLAY_THROW_IN,
            5: _SET_PLAY_PENALTY_KICK,
        }.get(set_play, _SET_PLAY_NONE)

    def _synthesize_secondary_state(self, msg: RoboCupGameControlRosData) -> int:
        if int(msg.set_play) != _SET_PLAY_NONE:
            return {
                _SET_PLAY_DIRECT_FREE_KICK: 4,
                _SET_PLAY_INDIRECT_FREE_KICK: 5,
                _SET_PLAY_PENALTY_KICK: 6,
                _SET_PLAY_CORNER_KICK: 7,
                _SET_PLAY_GOAL_KICK: 8,
                _SET_PLAY_THROW_IN: 9,
            }.get(int(msg.set_play), 0)
        return {
            0: 0,
            1: 1,
            2: 2,
            3: 3,
        }.get(int(msg.game_phase), 0)

    def _publish_direct_gc_topics(self, msg: RoboCupGameControlRosData) -> None:
        if not self._gc_direct_pubs:
            return
        team_index, opponent_team_index = self._resolve_gc_team_indices(msg)
        if team_index < 0 or opponent_team_index < 0:
            return

        single_msg = self._make_gc_identity_msg(msg, self._legacy_topic_robot_ids[0], team_index)
        self._gc_direct_pubs["single"].publish(single_msg)
        per_robot = self._gc_direct_pubs["per_robot"]
        for player_id, publisher in per_robot.items():
            publisher.publish(self._make_gc_identity_msg(msg, player_id, team_index))

    def _make_gc_identity_msg(
        self,
        msg: RoboCupGameControlRosData,
        player_id: int,
        team_index: int,
    ) -> RoboCupGameControlRosData:
        shaped = copy.deepcopy(msg)
        shaped.team_index = int(team_index)
        shaped.robot_index = max(0, min(19, player_id - 1))
        return shaped

    def _send_gc_return_packets(self) -> None:
        sock = self._gc_udp_sock
        if sock is None:
            return
        target_ip = self._gc_send_override_ip or self._gc_udp_last_sender_ip
        if not target_ip:
            return

        with self._lock:
            robots = [copy.deepcopy(robot) for robot in self._robots]
            ball = copy.deepcopy(self._ball)

        for robot in robots:
            rel_ball_x, rel_ball_y = self._to_local(
                {"x": robot.x, "y": robot.y, "theta": robot.theta},
                ball.x,
                ball.y,
            )
            packet = _GC_RETURN_STRUCT.pack(
                _GC_RETURN_STRUCT_HEADER,
                _GC_RETURN_STRUCT_VERSION,
                int(robot.player_id),
                int(self._team_number),
                0,
                float(robot.x * 1000.0),
                float(robot.y * 1000.0),
                float(robot.theta),
                0.0,
                float(rel_ball_x * 1000.0),
                float(rel_ball_y * 1000.0),
            )
            try:
                sock.sendto(packet, (target_ip, self._gc_return_port))
            except OSError as exc:
                self.get_logger().warn(f"Direct GC return send failed to {target_ip}:{self._gc_return_port}: {exc}",
                                       throttle_duration_sec=5.0)
                return

    def _cb_external_gc(self, msg: RoboCupGameControlRosData, topic: str) -> None:
        if msg.header == "sim":
            return
        if topic in self._owned_gc_topics and (
            time.monotonic() <= self._ignore_owned_gc_topics_until
            or
            self._direct_gc_udp_active() or self._is_recent_direct_gc_packet(int(msg.packet_number))
        ):
            return
        self._accept_external_gc(msg, topic)

    def _accept_external_gc(self, msg: RoboCupGameControlRosData, source: str) -> None:
        team_index, opponent_team_index = self._resolve_gc_team_indices(msg)
        if team_index < 0 or opponent_team_index < 0:
            self.get_logger().warn(
                f"Ignoring external GC on {source}: invalid team_index={int(msg.team_index)}",
                throttle_duration_sec=5.0,
            )
            return
        gc_state = ExternalGcState(
            msg=copy.deepcopy(msg),
            source_topic=source,
            received_at=time.monotonic(),
            team_index=team_index,
            opponent_team_index=opponent_team_index,
        )
        with self._lock:
            self._external_gc = gc_state
        if source != self._last_external_gc_source:
            ally_team_number = int(msg.teams[team_index].team_number)
            opponent_team_number = int(msg.teams[opponent_team_index].team_number)
            self.get_logger().info(
                "External GC linked: source=%s team=%d opponent=%d"
                % (source, ally_team_number, opponent_team_number),
            )
            self._last_external_gc_source = source

    def _resolve_gc_team_indices(self, msg: RoboCupGameControlRosData) -> tuple[int, int]:
        if len(msg.teams) < 2:
            return (-1, -1)
        for idx, team in enumerate(msg.teams[:2]):
            if int(team.team_number) == self._team_number:
                return (idx, 1 - idx)
        hinted = int(msg.team_index)
        if 0 <= hinted < 2 and int(msg.teams[hinted].team_number) > 0:
            return (hinted, 1 - hinted)
        return (-1, -1)

    def _get_external_gc_locked(self, now: float) -> ExternalGcState | None:
        if not self._external_gc_enabled or self._external_gc is None:
            return None
        if now - self._external_gc.received_at > self._external_gc_timeout:
            return None
        return self._external_gc

    def _gc_source_is_direct_udp(self, source: str) -> bool:
        return source.startswith("udp://")

    def _gc_motion_lock_reason_locked(self, now: float, gc: ExternalGcState | None = None) -> str:
        if not self._require_gc_for_motion:
            return ""
        if gc is None:
            gc = self._get_external_gc_locked(now)
        if gc is None:
            return "waiting_for_gc"
        if self._direct_gc_required_for_motion and self._receive_gc_direct_udp:
            if not self._gc_source_is_direct_udp(gc.source_topic):
                return "waiting_for_direct_gc"
            if not self._direct_gc_udp_active(now):
                return "waiting_for_direct_gc"
        return ""

    def _clone_external_gc_locked(self, now: float) -> ExternalGcState | None:
        gc = self._get_external_gc_locked(now)
        return copy.deepcopy(gc) if gc is not None else None

    def _build_gc_status_locked(self, now: float) -> dict:
        gc = self._get_external_gc_locked(now)
        motion_enabled = self._gc_motion_enabled_locked(now, gc)
        motion_lock_reason = self._gc_motion_lock_reason_locked(now, gc)
        if gc is None:
            return {
                "enabled": self._external_gc_enabled,
                "active": False,
                "controller": "waiting",
                "source": "",
                "age_sec": None,
                "packet_number": None,
                "state": None,
                "state_name": "inactive",
                "set_play": None,
                "set_play_name": "inactive",
                "stopped": False,
                "kicking_team": None,
                "kick_off_team": None,
                "team_number": self._team_number,
                "opponent_team_number": self._opponent_team_number,
                "team_index": 0,
                "opponent_team_index": 1,
                "ally_score": 0,
                "opponent_score": 0,
                "game_phase": None,
                "first_half": None,
                "secs_remaining": None,
                "secondary_time": None,
                "players_per_team": None,
                "competition_type": None,
                "ally_goalkeeper": None,
                "opponent_goalkeeper": None,
                "ally_penalized_players": [],
                "opponent_penalized_players": [],
                "requires_connection": self._require_gc_for_motion,
                "direct_gc_required_for_motion": self._direct_gc_required_for_motion,
                "motion_enabled": motion_enabled,
                "motion_lock_reason": motion_lock_reason,
                "receive_direct_udp": self._receive_gc_direct_udp,
                "direct_udp_active": self._direct_gc_udp_active(now),
                "publish_gc_ros_topics": self._publish_gc_ros_topics,
                "data_port": self._gc_data_port,
                "return_port": self._gc_return_port,
            }

        ally_team = gc.msg.teams[gc.team_index]
        opponent_team = gc.msg.teams[gc.opponent_team_index]
        return {
            "enabled": self._external_gc_enabled,
            "active": True,
            "controller": "direct_udp" if self._gc_source_is_direct_udp(gc.source_topic) else "external_topic",
            "source": gc.source_topic,
            "age_sec": round(max(0.0, now - gc.received_at), 3),
            "packet_number": int(gc.msg.packet_number),
            "state": int(gc.msg.state),
            "state_name": _STATE_NAMES.get(int(gc.msg.state), f"unknown_{int(gc.msg.state)}"),
            "set_play": int(gc.msg.set_play),
            "set_play_name": _SET_PLAY_NAMES.get(int(gc.msg.set_play), f"unknown_{int(gc.msg.set_play)}"),
            "stopped": bool(gc.msg.stopped),
            "kicking_team": int(gc.msg.kicking_team),
            "kick_off_team": int(gc.msg.kick_off_team),
            "team_number": int(ally_team.team_number),
            "opponent_team_number": int(opponent_team.team_number),
            "team_index": gc.team_index,
            "opponent_team_index": gc.opponent_team_index,
            "ally_score": int(ally_team.score),
            "opponent_score": int(opponent_team.score),
            "game_phase": int(gc.msg.game_phase),
            "first_half": int(gc.msg.first_half),
            "secs_remaining": int(gc.msg.secs_remaining),
            "secondary_time": int(gc.msg.secondary_time),
            "players_per_team": int(gc.msg.players_per_team),
            "competition_type": int(gc.msg.competition_type),
            "ally_goalkeeper": int(ally_team.goalkeeper),
            "opponent_goalkeeper": int(opponent_team.goalkeeper),
            "ally_penalized_players": [
                player_id
                for player_id, player in enumerate(ally_team.players, start=1)
                if int(player.penalty) != _PENALTY_NONE
            ],
            "opponent_penalized_players": [
                player_id
                for player_id, player in enumerate(opponent_team.players, start=1)
                if int(player.penalty) != _PENALTY_NONE
            ],
            "requires_connection": self._require_gc_for_motion,
            "direct_gc_required_for_motion": self._direct_gc_required_for_motion,
            "motion_enabled": motion_enabled,
            "motion_lock_reason": motion_lock_reason,
            "receive_direct_udp": self._receive_gc_direct_udp,
            "direct_udp_active": self._direct_gc_udp_active(now),
            "publish_gc_ros_topics": self._publish_gc_ros_topics,
            "data_port": self._gc_data_port,
            "return_port": self._gc_return_port,
        }

    def _team_penalty_map(self, team_info: TeamRosInfo) -> dict[int, int]:
        penalties: dict[int, int] = {}
        for player_id, player in enumerate(team_info.players, start=1):
            penalties[player_id] = int(player.penalty)
        return penalties

    def _snapshot_locked(self, now: float | None = None) -> dict:
        if now is None:
            now = time.monotonic()
        gc_status = self._build_gc_status_locked(now)
        return {
            "robots": [asdict(r) for r in self._robots],
            "opponents": [asdict(o) for o in self._opponents],
            "ball": asdict(self._ball),
            "paused": self._paused,
            "speed_mult": self._speed_mult,
            "field": {"length": self._field_l, "width": self._field_w},
            "manual": {
                "enabled": self._manual_enabled,
                "team": self._manual_target_team,
                "id": self._manual_target_id,
                "vx": self._manual_vx,
                "vy": self._manual_vy,
                "omega": self._manual_omega,
            },
            "legacy": {
                "enabled": self._publish_legacy_topics,
                "robot_ids": list(self._legacy_topic_robot_ids),
            },
            "publish_udp": self._publish_udp,
            "team_number": gc_status["team_number"],
            "opponent_team_number": gc_status["opponent_team_number"],
            "gc": gc_status,
            "noise": {
                "enabled": self._noise_enabled,
                "show_in_gui": self._noise_show_in_gui,
                "self_pos": self._noise_self_pos,
                "self_angle": self._noise_self_angle,
                "ball": self._noise_ball,
                "other_robot": self._noise_other_robot,
            },
            "fall": {
                "fall_prob": self._fall_prob,
                "recovery_sec": self._fall_recovery_sec,
                "robot_body_radius": self._robot_body_radius,
                "contact_distance": self._robot_contact_distance,
            },
            "fov": {
                "angle_deg": self._fov_angle_deg,
                "range_m": self._fov_range_m,
            },
            "perceived": self._build_perceived_locked(),
        }

    def get_state(self) -> dict:
        with self._lock:
            snapshot = self._snapshot_locked()
        return self._format_state(snapshot)

    def _format_state(self, snapshot: dict) -> dict:
        manual = snapshot["manual"]
        selected_ball = bool(manual["enabled"] and manual["team"] == "ball")

        def format_entity(raw: dict, idx: int) -> dict:
            team = raw["team"]
            if team == "ally":
                color = _ALLY_COLORS[(raw["player_id"] - 1) % len(_ALLY_COLORS)]
            else:
                color = _OPPONENT_COLORS[idx % len(_OPPONENT_COLORS)]
            action_idx = int(raw["action"])
            action_name = _ACTION_NAMES[action_idx] if 0 <= action_idx < len(_ACTION_NAMES) else "none"
            return {
                "id": raw["player_id"],
                "team": team,
                "label": ("Robot" if team == "ally" else "Opponent") + f" {raw['player_id']}",
                "x": round(raw["x"], 3),
                "y": round(raw["y"], 3),
                "theta": round(raw["theta"], 3),
                "role": raw["role"],
                "action": action_name,
                "penalty": bool(raw["penalty"]),
                "fallen": bool(raw.get("fallen", False)),
                "eval_mc": round(raw["eval_mc"], 3),
                "color": color,
                "selected": bool(
                    manual["enabled"]
                    and manual["team"] == team
                    and manual["id"] == raw["player_id"]
                ),
            }

        robots = [format_entity(r, i) for i, r in enumerate(snapshot["robots"])]
        opponents = [format_entity(o, i) for i, o in enumerate(snapshot["opponents"])]
        return {
            "robots": robots,
            "opponents": opponents,
            "ball": {
                "x": round(snapshot["ball"]["x"], 3),
                "y": round(snapshot["ball"]["y"], 3),
                "vx": round(snapshot["ball"]["vx"], 3),
                "vy": round(snapshot["ball"]["vy"], 3),
                "selected": selected_ball,
            },
            "paused": snapshot["paused"],
            "speed_mult": snapshot["speed_mult"],
            "field": snapshot["field"],
            "manual": manual,
            "legacy": snapshot["legacy"],
            "publish_udp": snapshot["publish_udp"],
            "gc": snapshot["gc"],
            "noise": snapshot["noise"],
            "fall": snapshot["fall"],
            "fov": snapshot["fov"],
            "perceived": {
                str(pid): {
                    "x": round(p["x"], 3),
                    "y": round(p["y"], 3),
                    "theta": round(p["theta"], 3),
                    "ball_x": round(p["ball_x"], 3) if p["ball_x"] is not None else None,
                    "ball_y": round(p["ball_y"], 3) if p["ball_y"] is not None else None,
                    "ball_in_fov": p.get("ball_in_fov", True),
                    "allies": [
                        {"id": a["id"], "x": round(a["x"], 3), "y": round(a["y"], 3)}
                        for a in p.get("allies", [])
                    ],
                    "opponents": [
                        {"id": a["id"], "x": round(a["x"], 3), "y": round(a["y"], 3)}
                        for a in p.get("opponents", [])
                    ],
                }
                for pid, p in snapshot["perceived"].items()
            },
        }

    def override_agent(self, team: str, pid: int, x: float, y: float, theta: float) -> bool:
        expires = time.monotonic() + self._override_duration
        with self._lock:
            agent = self._find_agent(team, pid)
            if agent is None:
                return False
            agent.override_x = x
            agent.override_y = y
            agent.override_theta = self._wrap_angle(theta)
            agent.override_expires = expires
            agent.orbit_angle = math.atan2(y - agent.orbit_cy, x - agent.orbit_cx)
            agent.target_x = x
            agent.target_y = y
            return True

    def override_ball(self, x: float, y: float) -> None:
        expires = time.monotonic() + self._override_duration
        with self._lock:
            self._ball.override_x = x
            self._ball.override_y = y
            self._ball.override_expires = expires
            self._ball.vx = 0.0
            self._ball.vy = 0.0
            self._ball.kick_until = 0.0
            self._ball.kick_cooldown_until = 0.0
            self._ball.last_kick_at = 0.0
            self._ball.last_kicker_team = ""
            self._ball.bypass_block_until = 0.0
            self._ball.bypass_block_team = ""

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self._paused = paused

    def set_speed(self, mult: float) -> None:
        with self._lock:
            self._speed_mult = max(0.1, min(10.0, mult))

    def set_manual_target(self, team: str, pid: int, enabled: bool) -> bool:
        with self._lock:
            if not enabled or team == "none":
                self._clear_manual_locked()
                return True
            if team == "ball":
                self._manual_enabled = True
                self._manual_target_team = "ball"
                self._manual_target_id = 0
                self._manual_vx = 0.0
                self._manual_vy = 0.0
                self._manual_omega = 0.0
                return True
            if team not in {"ally", "opponent"}:
                return False
            if self._find_agent(team, pid) is None:
                return False
            self._manual_enabled = True
            self._manual_target_team = team
            self._manual_target_id = pid
            self._manual_vx = 0.0
            self._manual_vy = 0.0
            self._manual_omega = 0.0
            return True

    def set_manual_command(self, vx: float, vy: float, omega: float) -> None:
        with self._lock:
            self._manual_vx = max(-1.0, min(1.0, vx))
            self._manual_vy = max(-1.0, min(1.0, vy))
            self._manual_omega = max(-1.0, min(1.0, omega))

    @staticmethod
    def _parse_legacy_robot_ids(csv_text: str, num_robots: int) -> list[int]:
        ids: list[int] = []
        for raw in csv_text.split(","):
            text = raw.strip()
            if not text:
                continue
            try:
                robot_id = int(text)
            except ValueError:
                continue
            if 1 <= robot_id <= num_robots and robot_id not in ids:
                ids.append(robot_id)
        return ids

    def set_legacy_robot_id(self, new_id: int) -> bool:
        return self.set_legacy_robot_ids([new_id])

    def set_legacy_robot_ids(self, ids: list[int]) -> bool:
        valid = sorted({i for i in ids if 1 <= i <= self._num_robots})
        if not valid:
            return False
        with self._lock:
            self._legacy_topic_robot_ids = valid
        return True

    def reset(self) -> None:
        with self._lock:
            self._robots = self._init_agents("ally", self._num_robots)
            self._opponents = self._init_agents("opponent", self._num_opponents)
            b = self._init_ball
            self._ball = BallState(x=b.x, y=b.y, vx=b.vx, vy=b.vy)
            self._paused = False
            self._speed_mult = 1.0
            self._kickoff_release_pending = False
            self._reset_kickoff_release_tracking_locked()
            self._reset_kickoff_plan_locked()
            self._clear_manual_locked()

    def _clear_manual_locked(self) -> None:
        self._manual_enabled = False
        self._manual_target_team = "none"
        self._manual_target_id = 0
        self._manual_vx = 0.0
        self._manual_vy = 0.0
        self._manual_omega = 0.0

    def _find_agent(self, team: str, pid: int) -> AgentState | None:
        group = self._robots if team == "ally" else self._opponents
        for agent in group:
            if agent.player_id == pid:
                return agent
        return None

    def _cb_ball_pose(self, msg: Pose2D) -> None:
        self.override_ball(msg.x, msg.y)

    def _tick(self) -> None:
        try:
            self._tick_impl()
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f"_tick error: {exc}", throttle_duration_sec=2.0)

    def _tick_impl(self) -> None:
        now = time.monotonic()
        with self._lock:
            paused = self._paused
            speed_mult = self._speed_mult

        dt = min(now - self._last_tick, 0.2) * speed_mult
        self._last_tick = now

        if paused:
            return

        with self._lock:
            gc = self._get_external_gc_locked(now)
            gc_motion_enabled = self._gc_motion_enabled_locked(now, gc)
            self._update_kickoff_phase_locked(now, gc if gc_motion_enabled else None)
            self._sync_gc_penalties_locked(gc if gc_motion_enabled else None)
            if gc_motion_enabled:
                self._update_falls_locked(now)
                for robot in self._robots:
                    if robot.fallen:
                        self._hold_agent(robot)
                    else:
                        self._update_agent(robot, dt, gc)
                for opponent in self._opponents:
                    if opponent.fallen:
                        self._hold_agent(opponent)
                    else:
                        self._update_agent(opponent, dt, gc)
                contact_pairs = self._resolve_agent_contacts_locked()
                self._update_falls_locked(now, contact_pairs)
                self._update_ball(dt, gc)
                self._apply_kicks(now, gc)
            else:
                self._hold_ball(self._ball)
                for robot in self._robots:
                    self._hold_agent(robot)
                for opponent in self._opponents:
                    self._hold_agent(opponent)
            snapshot = self._snapshot_locked(now)

        if self._publish_udp:
            for pkt, addr in self._build_udp_packets(snapshot):
                try:
                    self._sock.sendto(pkt, addr)
                except OSError as exc:
                    self.get_logger().warn(f"UDP send failed: {exc}", throttle_duration_sec=5.0)

        if self._publish_legacy_topics:
            self._publish_legacy_snapshot(snapshot)

    def _sync_gc_penalties_locked(self, gc: ExternalGcState | None) -> None:
        ally_penalties: dict[int, int] = {}
        opponent_penalties: dict[int, int] = {}
        if gc is not None:
            ally_penalties = self._team_penalty_map(gc.msg.teams[gc.team_index])
            opponent_penalties = self._team_penalty_map(gc.msg.teams[gc.opponent_team_index])
        for agent in self._robots:
            agent.penalty = ally_penalties.get(agent.player_id, _PENALTY_NONE) != _PENALTY_NONE
        for agent in self._opponents:
            agent.penalty = opponent_penalties.get(agent.player_id, _PENALTY_NONE) != _PENALTY_NONE

    def _gc_motion_enabled_locked(self, now: float, gc: ExternalGcState | None = None) -> bool:
        if not self._require_gc_for_motion:
            return True
        if gc is None:
            gc = self._get_external_gc_locked(now)
        if gc is None:
            return False
        if self._direct_gc_required_for_motion and self._receive_gc_direct_udp:
            return self._gc_source_is_direct_udp(gc.source_topic) and self._direct_gc_udp_active(now)
        return True

    def _gc_motion_mode(self, gc: ExternalGcState) -> str:
        if int(gc.msg.stopped) == 1:
            return "stopped"
        state = int(gc.msg.state)
        if state == _STATE_INITIAL:
            return "initial"
        if state == _STATE_STANDBY:
            return "standby"
        if state == _STATE_READY:
            return "ready"
        if state == _STATE_SET:
            return "set"
        if state == _STATE_PLAYING:
            return "play"
        return "hold"

    def _reset_kickoff_release_tracking_locked(self) -> None:
        self._kickoff_release_started_at = 0.0
        self._kickoff_release_origin_x = 0.0
        self._kickoff_release_origin_y = 0.0
        self._kickoff_release_origin_fixed = False

    def _reset_kickoff_plan_locked(self) -> None:
        self._kickoff_plan_started_at = 0.0
        self._kickoff_plan_team_number = 0
        self._kickoff_plan_completed = False

    def _complete_kickoff_plan_locked(self) -> None:
        self._kickoff_plan_started_at = 0.0
        self._kickoff_plan_team_number = 0
        self._kickoff_plan_completed = True

    def _sync_agent_action_state(self, agent: AgentState, now: float | None = None) -> None:
        if now is None:
            now = time.monotonic()
        if int(agent.action) == 5:
            if agent.dribble_since <= 0.0:
                agent.dribble_since = now
        else:
            agent.dribble_since = 0.0

    def _angle_error_deg(self, source_theta: float, target_theta: float) -> float:
        return abs(math.degrees(self._wrap_angle(target_theta - source_theta)))

    def _ball_is_in_front_of_agent(self, agent: AgentState, half_angle_deg: float) -> bool:
        dx = self._ball.x - agent.x
        dy = self._ball.y - agent.y
        distance = math.hypot(dx, dy)
        if distance < 1e-4:
            return True
        bearing = math.atan2(dy, dx)
        return self._angle_error_deg(agent.theta, bearing) <= half_angle_deg

    def _find_active_dribbler(self) -> AgentState | None:
        now = time.monotonic()
        candidates: list[tuple[float, AgentState]] = []
        for agent in [*self._robots, *self._opponents]:
            if (
                agent.penalty
                or agent.fallen
                or int(agent.action) != 5
                or self._ball_control_blocked(agent.team, now)
            ):
                continue
            distance_to_ball = math.hypot(agent.x - self._ball.x, agent.y - self._ball.y)
            hold_pos_x = agent.x + math.cos(agent.theta) * _DEFAULT_DRIBBLE_HOLD_DISTANCE
            hold_pos_y = agent.y + math.sin(agent.theta) * _DEFAULT_DRIBBLE_HOLD_DISTANCE
            hold_dist_to_ball = math.hypot(hold_pos_x - self._ball.x, hold_pos_y - self._ball.y)
            if (
                distance_to_ball <= max(_DEFAULT_DRIBBLE_CAPTURE_RADIUS, self._motion_cfg.ball_capture_threshold + 0.2)
                and hold_dist_to_ball <= _DEFAULT_DRIBBLE_CAPTURE_RADIUS
                and self._ball_is_in_front_of_agent(agent, _DEFAULT_DRIBBLE_FRONT_CONE_HALF_DEG)
            ):
                candidates.append((distance_to_ball, agent))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[0])[1]

    def _update_ball(self, dt: float, gc: ExternalGcState | None) -> None:
        ball = self._ball
        now = time.monotonic()
        if self._manual_enabled and self._manual_target_team == "ball":
            self._update_manual_ball(ball, dt)
            return
        if ball.override_x is not None and now < ball.override_expires:
            ball.x = ball.override_x
            ball.y = ball.override_y
            return
        if gc is not None:
            gc_mode = self._gc_motion_mode(gc)
            if gc_mode in {"initial", "standby", "hold"}:
                self._place_ball_center(ball)
                return
            if gc_mode == "ready":
                self._place_ball_center(ball)
                return
            if gc_mode == "set":
                if int(gc.msg.set_play) == _SET_PLAY_NONE:
                    self._place_ball_center(ball)
                else:
                    ball.vx = 0.0
                    ball.vy = 0.0
                return
        if gc is not None and self._gc_motion_mode(gc) != "play":
            ball.vx = 0.0
            ball.vy = 0.0
            ball.kick_until = 0.0
            return
        kicked_motion = now < ball.kick_until
        dribbler = None if kicked_motion else self._find_active_dribbler()
        if gc is not None and self._kickoff_release_pending and now >= ball.kick_until and dribbler is None:
            ball.vx = 0.0
            ball.vy = 0.0
            return
        if dribbler is not None:
            hold_x = dribbler.x + math.cos(dribbler.theta) * _DEFAULT_DRIBBLE_HOLD_DISTANCE
            hold_y = dribbler.y + math.sin(dribbler.theta) * _DEFAULT_DRIBBLE_HOLD_DISTANCE
            hold_x, hold_y = self._clamp_point(hold_x, hold_y, margin=0.35)
            if dt > 1e-4:
                ball.vx = (hold_x - ball.x) / dt
                ball.vy = (hold_y - ball.y) / dt
            else:
                ball.vx = 0.0
                ball.vy = 0.0
            ball.x = hold_x
            ball.y = hold_y
            ball.kick_until = 0.0
            return
        if kicked_motion:
            drag = max(0.0, 1.0 - 1.15 * dt)
            ball.vx *= drag
            ball.vy *= drag
        else:
            drag = max(0.0, 1.0 - 4.0 * dt)
            ball.vx *= drag
            ball.vy *= drag
        speed = math.hypot(ball.vx, ball.vy)
        max_speed = _DEFAULT_KICK_SPEED if kicked_motion else 1.2
        if speed > max_speed:
            ball.vx = ball.vx / speed * max_speed
            ball.vy = ball.vy / speed * max_speed
        prev_x = ball.x
        prev_y = ball.y
        ball.x += ball.vx * dt
        ball.y += ball.vy * dt
        self._constrain_ball_position(ball, prev_x, prev_y)
        if kicked_motion and math.hypot(ball.vx, ball.vy) < 0.35:
            ball.kick_until = 0.0
        if not kicked_motion and math.hypot(ball.vx, ball.vy) < 0.02:
            ball.vx = 0.0
            ball.vy = 0.0

    def _update_manual_ball(self, ball: BallState, dt: float) -> None:
        linear_speed = 2.2
        ball.kick_until = 0.0
        ball.vx = self._manual_vx * linear_speed
        ball.vy = self._manual_vy * linear_speed
        prev_x = ball.x
        prev_y = ball.y
        ball.x += ball.vx * dt
        ball.y += ball.vy * dt
        self._constrain_ball_position(ball, prev_x, prev_y)

    def _bounce_ball_x(self, ball: BallState, wall_x: float) -> None:
        wall_sign = math.copysign(1.0, wall_x)
        ball.x = wall_x
        if ball.vx * wall_sign > 0.0:
            ball.vx = -ball.vx * _DEFAULT_BALL_WALL_RESTITUTION

    def _bounce_ball_y(self, ball: BallState, wall_y: float) -> None:
        wall_sign = math.copysign(1.0, wall_y)
        ball.y = wall_y
        if ball.vy * wall_sign > 0.0:
            ball.vy = -ball.vy * _DEFAULT_BALL_WALL_RESTITUTION

    def _constrain_ball_position(self, ball: BallState, prev_x: float, prev_y: float) -> None:
        field_half_l = self._field_l / 2
        field_half_w = self._field_w / 2
        goal_back_limit = field_half_l + 3.0
        goal_half_width = max(0.1, min(field_half_w, self._motion_cfg.goal_half_width))

        if abs(ball.x) > goal_back_limit:
            self._bounce_ball_x(ball, math.copysign(goal_back_limit, ball.x))

        if abs(ball.x) <= field_half_l:
            if abs(ball.y) > field_half_w:
                self._bounce_ball_y(ball, math.copysign(field_half_w, ball.y))
            return

        if abs(ball.y) <= goal_half_width:
            return

        was_behind_goal = abs(prev_x) > field_half_l
        was_in_goal_lane = abs(prev_y) <= goal_half_width
        if was_behind_goal and was_in_goal_lane:
            self._bounce_ball_y(ball, math.copysign(goal_half_width, ball.y))
            return

        self._bounce_ball_x(ball, math.copysign(field_half_l, ball.x))
        if abs(ball.y) > field_half_w:
            self._bounce_ball_y(ball, math.copysign(field_half_w, ball.y))

    def _update_agent(self, agent: AgentState, dt: float, gc: ExternalGcState | None) -> None:
        if self._manual_enabled and self._manual_target_team == agent.team and self._manual_target_id == agent.player_id:
            self._update_manual_agent(agent, dt)
            return

        now = time.monotonic()
        if agent.override_x is not None and now < agent.override_expires:
            agent.x = agent.override_x
            agent.y = agent.override_y
            agent.theta = agent.override_theta or agent.theta
            agent.target_x = agent.x
            agent.target_y = agent.y
            self._update_action(agent, manual=False)
            return

        if agent.penalty:
            self._hold_agent(agent)
            return

        if gc is not None:
            gc_mode = self._gc_motion_mode(gc)
            if gc_mode in {"initial", "standby"}:
                kicking_team = int(gc.msg.kicking_team)
                if kicking_team != 0:
                    # Kickoff team assigned: auto-place in staging position within own half
                    target_x, target_y, target_theta = self._get_kickoff_staging_pose(agent, gc)
                else:
                    # No kickoff team assigned: touchline waiting position
                    team_idx = gc.team_index if agent.team == "ally" else gc.opponent_team_index
                    target_x, target_y, target_theta = self._get_waiting_pose(
                        agent.team,
                        agent.player_id,
                        int(agent.role),
                        self._num_robots if agent.team == "ally" else self._num_opponents,
                        team_index=team_idx,
                    )
                self._apply_static_pose(agent, target_x, target_y, target_theta)
                return
            if gc_mode == "ready":
                target_x, target_y, target_theta = self._get_gc_target_pose(agent, gc)
                self._move_agent_to_pose(agent, target_x, target_y, target_theta, dt, 1.55 if agent.team == "ally" else 1.45)
                return
            if gc_mode == "set":
                target_x, target_y, target_theta = self._get_gc_target_pose(agent, gc)
                self._move_agent_to_pose(
                    agent,
                    target_x,
                    target_y,
                    target_theta,
                    dt,
                    1.15 if agent.team == "ally" else 1.05,
                    prefer_heading=True,
                    heading_only_angle_deg=_DEFAULT_DRIBBLE_STEER_ENTER_DEG,
                )
                return
            if gc_mode in {"play", "stopped"}:
                self._update_gc_play_agent(agent, dt, gc)
                return
            # Unknown states outside initial/standby/ready/set fall through to play strategy
            if gc_mode not in {"initial", "standby", "ready", "set"}:
                self._update_gc_play_agent(agent, dt, gc)
                return

        # Waypoint wandering: pick a new destination on arrival or timer expiry
        dist_to_wp = math.hypot(agent.wander_target_x - agent.x, agent.wander_target_y - agent.y)
        if dist_to_wp < 0.5 or now >= agent.wander_next:
            wl = self._field_l / 2 - 0.9
            ww = self._field_w / 2 - 0.6
            agent.wander_target_x = random.uniform(-wl, wl)
            agent.wander_target_y = random.uniform(-ww, ww)
            agent.wander_next = now + random.uniform(8.0, 16.0)

        # Smooth ball attraction: weight fades linearly with distance (no step)
        dist_to_ball = math.hypot(self._ball.x - agent.x, self._ball.y - agent.y)
        target_x = agent.wander_target_x
        target_y = agent.wander_target_y
        ball_attract_range = 3.0
        if dist_to_ball < ball_attract_range:
            ball_blend = 0.45 * (1.0 - dist_to_ball / ball_attract_range)
            target_x = target_x * (1.0 - ball_blend) + self._ball.x * ball_blend
            target_y = target_y * (1.0 - ball_blend) + self._ball.y * ball_blend
        agent.target_x = target_x
        agent.target_y = target_y

        dx = target_x - agent.x
        dy = target_y - agent.y
        dist = math.hypot(dx, dy)
        max_speed = 2.2 if agent.team == "ally" else 2.0

        if dist > 0.01:
            desired_vx = dx / dist * max_speed
            desired_vy = dy / dist * max_speed
        else:
            desired_vx = 0.0
            desired_vy = 0.0
        dvx = desired_vx - agent.vel_x
        dvy = desired_vy - agent.vel_y
        dv = math.hypot(dvx, dvy)
        if dv > 1e-6:
            agent.vel_x += dvx / dv * min(dv, 7.0 * dt)
            agent.vel_y += dvy / dv * min(dv, 7.0 * dt)
        agent.x += agent.vel_x * dt
        agent.y += agent.vel_y * dt
        if math.hypot(agent.vel_x, agent.vel_y) > 0.08:
            agent.theta = math.atan2(agent.vel_y, agent.vel_x)
        self._clamp_agent(agent)
        self._update_action(agent, manual=False)

    def _hold_agent(self, agent: AgentState) -> None:
        agent.target_x = agent.x
        agent.target_y = agent.y
        agent.action = 0
        agent.kick_latched = False
        agent.vel_x = 0.0
        agent.vel_y = 0.0
        self._sync_agent_action_state(agent)

    def _hold_ball(self, ball: BallState) -> None:
        ball.vx = 0.0
        ball.vy = 0.0
        ball.kick_until = 0.0

    def _set_agent_fallen(self, agent: AgentState, now: float) -> None:
        agent.fallen = True
        agent.fallen_at = now
        self._hold_agent(agent)

    def _place_ball_center(self, ball: BallState) -> None:
        ball.x = 0.0
        ball.y = 0.0
        ball.vx = 0.0
        ball.vy = 0.0
        ball.kick_until = 0.0

    def _kick_cooldown_active(self, now: float | None = None) -> bool:
        if now is None:
            now = time.monotonic()
        return now < self._ball.kick_cooldown_until

    def _ball_control_blocked(self, team: str, now: float | None = None) -> bool:
        if now is None:
            now = time.monotonic()
        return now < self._ball.bypass_block_until and team == self._ball.bypass_block_team

    def _resolve_agent_contacts_locked(self) -> list[tuple[AgentState, AgentState, float]]:
        agents = [*self._robots, *self._opponents]
        if len(agents) < 2:
            return []

        min_distance = self._robot_body_radius * 2.0
        contact_distance = max(min_distance, self._robot_contact_distance)
        contacts: list[tuple[AgentState, AgentState, float]] = []
        seen_pairs: set[tuple[str, int, str, int]] = set()

        for _ in range(_DEFAULT_CONTACT_RESOLVE_PASSES):
            adjusted = False
            for index, first in enumerate(agents[:-1]):
                for second in agents[index + 1:]:
                    dx = second.x - first.x
                    dy = second.y - first.y
                    distance = math.hypot(dx, dy)
                    pair_key = (first.team, first.player_id, second.team, second.player_id)
                    if distance < contact_distance and pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        contacts.append((first, second, distance))
                    if distance >= min_distance:
                        continue

                    if distance <= 1e-6:
                        sep_theta = random.uniform(-math.pi, math.pi)
                        nx = math.cos(sep_theta)
                        ny = math.sin(sep_theta)
                    else:
                        nx = dx / distance
                        ny = dy / distance

                    overlap = min_distance - distance
                    push = overlap * 0.5
                    first.x -= nx * push
                    first.y -= ny * push
                    second.x += nx * push
                    second.y += ny * push
                    first.vel_x *= 0.6
                    first.vel_y *= 0.6
                    second.vel_x *= 0.6
                    second.vel_y *= 0.6
                    self._clamp_agent(first)
                    self._clamp_agent(second)
                    adjusted = True
            if not adjusted:
                break

        return contacts

    def _apply_kicks(self, now: float, gc: ExternalGcState | None) -> None:
        ball_speed = math.hypot(self._ball.vx, self._ball.vy)
        if now < self._ball.kick_until or ball_speed > _DEFAULT_KICK_CONTROL_SPEED_MAX:
            return
        kick_cooldown_active = self._kick_cooldown_active(now)
        candidates: list[tuple[float, AgentState]] = []
        for agent in [*self._robots, *self._opponents]:
            distance_to_ball = math.hypot(agent.x - self._ball.x, agent.y - self._ball.y)
            kick_active = (
                not agent.penalty
                and not agent.fallen
                and int(agent.action) == 3
                and distance_to_ball <= _DEFAULT_KICK_CONTACT_RADIUS
            )
            if not kick_active:
                agent.kick_latched = False
                continue
            if agent.kick_latched and not kick_cooldown_active:
                agent.kick_latched = False
            if agent.kick_latched:
                continue
            if self._ball_control_blocked(agent.team, now):
                continue
            if kick_cooldown_active:
                continue
            candidates.append((distance_to_ball, agent))

        if not candidates:
            return

        _, kicker = min(candidates, key=lambda item: item[0])
        self._kick_ball_from_agent(kicker, now, gc)
        kicker.kick_latched = True

    def _kick_ball_from_agent(self, agent: AgentState, now: float, gc: ExternalGcState | None) -> None:
        ball = self._ball
        ball.last_kick_at = now
        ball.kick_cooldown_until = now + _DEFAULT_RECIPROCAL_KICK_COOLDOWN
        ball.last_kicker_team = agent.team
        dir_x, dir_y = self._get_kick_direction(agent, gc)
        release_push_distance = max(
            _DEFAULT_KICK_PUSH_DISTANCE,
            _DEFAULT_KICK_CONTACT_RADIUS + 0.08,
        )
        ball.x, ball.y = self._clamp_point(
            ball.x + dir_x * release_push_distance,
            ball.y + dir_y * release_push_distance,
            margin=0.35,
        )
        # Set post-push position as origin so cooldown distance excludes the push distance
        ball.last_kick_origin_x = ball.x
        ball.last_kick_origin_y = ball.y
        ball.vx = dir_x * _DEFAULT_KICK_SPEED
        ball.vy = dir_y * _DEFAULT_KICK_SPEED
        ball.kick_until = now + _DEFAULT_KICK_ACTIVE_SEC
        self._kickoff_release_pending = False
        # Bypass kick with a nearby opponent: additionally block the opposing team for 1.8 s
        opp_group = self._opponents if agent.team == "ally" else self._robots
        close_opp = any(
            math.hypot(opp.x - ball.x, opp.y - ball.y) < 2.2
            for opp in opp_group
            if not opp.penalty and not opp.fallen
        )
        if close_opp:
            ball.bypass_block_until = now + _DEFAULT_RECIPROCAL_KICK_COOLDOWN
            ball.bypass_block_team = "opponent" if agent.team == "ally" else "ally"

    def _get_kick_direction(self, agent: AgentState, gc: ExternalGcState | None) -> tuple[float, float]:
        del gc
        sample_distance = _DEFAULT_RECIPROCAL_KICK_RELEASE_DISTANCE
        heading_x = math.cos(agent.theta)
        heading_y = math.sin(agent.theta)
        preferred_x = heading_x
        preferred_y = heading_y
        escape_dir = self._ball_escape_direction_from_walls()
        if escape_dir is not None:
            preferred_x = (0.55 * heading_x) + (1.15 * escape_dir[0])
            preferred_y = (0.55 * heading_y) + (1.15 * escape_dir[1])
            preferred_norm = math.hypot(preferred_x, preferred_y)
            if preferred_norm > 1e-6:
                preferred_x /= preferred_norm
                preferred_y /= preferred_norm
            else:
                preferred_x, preferred_y = escape_dir
        preferred_theta = math.atan2(preferred_y, preferred_x)

        # If a nearby opponent is directly in the kick path, deflect preferred_theta to go around them
        opponents = self._opponents if agent.team == "ally" else self._robots
        all_other_agents = [
            other
            for other in [*self._robots, *self._opponents]
            if not (other.team == agent.team and other.player_id == agent.player_id)
        ]
        probe_half_l, probe_half_w = self._robot_field_extent(margin=0.0)
        _BYPASS_THREAT_RANGE = 2.2   # Only opponents within this distance are considered threats
        _BYPASS_CONE_RAD = math.radians(65.0)  # Must be within this angle to count as a threat

        def _direction_space_score(theta: float) -> float:
            dir_x = math.cos(theta)
            dir_y = math.sin(theta)
            candidate_x = self._ball.x + dir_x * sample_distance
            candidate_y = self._ball.y + dir_y * sample_distance
            min_clearance = math.inf
            min_path_clearance = math.inf
            threat_penalty = 0.0
            wall_space = 0.0

            for probe_distance in (sample_distance, sample_distance * 2.0, sample_distance * 3.0):
                probe_x = self._ball.x + dir_x * probe_distance
                probe_y = self._ball.y + dir_y * probe_distance
                wall_space += min(probe_half_l - abs(probe_x), probe_half_w - abs(probe_y))

            for other in all_other_agents:
                clearance = math.hypot(candidate_x - other.x, candidate_y - other.y)
                min_clearance = min(min_clearance, clearance)
                rel_x = other.x - self._ball.x
                rel_y = other.y - self._ball.y
                along = max(0.0, min(sample_distance, (rel_x * dir_x) + (rel_y * dir_y)))
                closest_x = self._ball.x + (dir_x * along)
                closest_y = self._ball.y + (dir_y * along)
                path_clearance = math.hypot(other.x - closest_x, other.y - closest_y)
                min_path_clearance = min(min_path_clearance, path_clearance)

                distance = math.hypot(rel_x, rel_y)
                if distance <= 1e-6:
                    continue
                other_angle = math.atan2(rel_y, rel_x)
                angle_error = abs(self._wrap_angle(other_angle - theta))
                if angle_error >= _BYPASS_CONE_RAD:
                    continue
                frontal = 1.0 - (angle_error / _BYPASS_CONE_RAD)
                proximity = max(0.0, 1.0 - (distance / (_BYPASS_THREAT_RANGE + 0.8)))
                team_weight = 1.8 if other.team != agent.team else 0.8
                threat_penalty += team_weight * frontal * proximity

            alignment = (dir_x * heading_x) + (dir_y * heading_y)
            return (
                1.25 * (min_path_clearance if not math.isinf(min_path_clearance) else sample_distance)
                + 0.35 * (min_clearance if not math.isinf(min_clearance) else sample_distance)
                + 0.28 * wall_space
                + 0.15 * alignment
                - threat_penalty
            )

        closest_threat = None
        closest_dist = math.inf
        for opp in opponents:
            if opp.penalty or opp.fallen:
                continue
            d = math.hypot(opp.x - self._ball.x, opp.y - self._ball.y)
            if d >= _BYPASS_THREAT_RANGE or d >= closest_dist:
                continue
            to_opp = math.atan2(opp.y - self._ball.y, opp.x - self._ball.x)
            if abs(self._wrap_angle(to_opp - preferred_theta)) < _BYPASS_CONE_RAD:
                closest_dist = d
                closest_threat = opp

        if closest_threat is not None:
            to_opp_angle = math.atan2(
                closest_threat.y - self._ball.y,
                closest_threat.x - self._ball.x,
            )
            cross = math.sin(self._wrap_angle(to_opp_angle - preferred_theta))
            head_on_duel = abs(cross) < 0.15
            # Deflect more sharply the closer the opponent is; aim wider to the side in a head-on duel.
            bypass_frac = max(0.0, 1.0 - closest_dist / _BYPASS_THREAT_RANGE)
            bypass_angle_deg = (65.0 if head_on_duel else 55.0) + 30.0 * bypass_frac
            bypass_angle = math.radians(min(95.0, bypass_angle_deg))
            if head_on_duel:
                # In a head-on duel, pick whichever of the two bypass directions is actually more open.
                angle_plus = self._wrap_angle(preferred_theta + bypass_angle)
                angle_minus = self._wrap_angle(preferred_theta - bypass_angle)
                deflect_sign = 1.0 if _direction_space_score(angle_plus) >= _direction_space_score(angle_minus) else -1.0
            else:
                deflect_sign = -math.copysign(1.0, cross)
            preferred_theta = self._wrap_angle(preferred_theta + deflect_sign * bypass_angle)
            # Reduce jitter the closer the opponent is, to focus the kick direction
            effective_jitter = _DEFAULT_KICK_DIRECTION_JITTER_RAD * (1.0 - 0.6 * bypass_frac)
            if head_on_duel:
                effective_jitter = min(effective_jitter, math.radians(12.0))
        else:
            effective_jitter = _DEFAULT_KICK_DIRECTION_JITTER_RAD

        best_dir = (math.cos(preferred_theta), math.sin(preferred_theta))
        best_score = _direction_space_score(preferred_theta)

        for _ in range(_DEFAULT_KICK_DIRECTION_SAMPLE_COUNT):
            random_angle = preferred_theta + random.uniform(
                -effective_jitter,
                effective_jitter,
            )
            score = _direction_space_score(random_angle)
            if score > best_score:
                best_score = score
                best_dir = (math.cos(random_angle), math.sin(random_angle))

        return best_dir

    def _move_agent_to_pose(
        self,
        agent: AgentState,
        target_x: float,
        target_y: float,
        target_theta: float,
        dt: float,
        max_speed: float,
        prefer_heading: bool = False,
        heading_only_angle_deg: float = 180.0,
    ) -> None:
        agent.target_x = target_x
        agent.target_y = target_y
        turn_error = self._wrap_angle(target_theta - agent.theta)
        turn_error_deg = abs(math.degrees(turn_error))
        dx = target_x - agent.x
        dy = target_y - agent.y
        dist = math.hypot(dx, dy)

        if dist > 0.01:
            speed = min(max_speed, max(0.25, dist / 0.35))
            if prefer_heading:
                # Keep moving, but scale speed down proportionally to heading error
                angle_scale = max(0.15, 1.0 - min(1.0, turn_error_deg / max(heading_only_angle_deg, 1.0)))
                speed *= angle_scale
            desired_vx = dx / dist * speed
            desired_vy = dy / dist * speed
            dvx = desired_vx - agent.vel_x
            dvy = desired_vy - agent.vel_y
            dv = math.hypot(dvx, dvy)
            if dv > 1e-6:
                applied = min(dv, 8.0 * dt)
                agent.vel_x += dvx / dv * applied
                agent.vel_y += dvy / dv * applied
            agent.x += agent.vel_x * dt
            agent.y += agent.vel_y * dt
            # When prefer_heading=False, naturally face the direction of movement
            if not prefer_heading and dist > 0.08:
                agent.theta = math.atan2(dy, dx)
        else:
            agent.vel_x *= max(0.0, 1.0 - 12.0 * dt)
            agent.vel_y *= max(0.0, 1.0 - 12.0 * dt)

        turn_error = self._wrap_angle(target_theta - agent.theta)
        max_turn = 2.8 * dt
        if abs(turn_error) > 0.02:
            turn_step = max(-max_turn, min(max_turn, turn_error))
            agent.theta = self._wrap_angle(agent.theta + turn_step)

        self._clamp_agent(agent)

        if dist > 0.08:
            agent.action = 1  # Moving — always move_to
        else:
            agent.action = 0
        self._sync_agent_action_state(agent)

    def _get_gc_target_pose(self, agent: AgentState, gc: ExternalGcState) -> tuple[float, float, float]:
        if agent.team == "ally":
            team_index = gc.team_index
            team_info = gc.msg.teams[gc.team_index]
            team_number = int(team_info.team_number)
        else:
            team_index = gc.opponent_team_index
            team_info = gc.msg.teams[gc.opponent_team_index]
            team_number = int(team_info.team_number)

        is_goalkeeper = agent.player_id == int(team_info.goalkeeper) or int(agent.role) == 2
        if is_goalkeeper:
            base_pose = self._rule_goalkeeper_pose()
        else:
            has_kickoff_rights = int(gc.msg.kicking_team) == team_number
            field_player_rank = self._field_player_rank(agent, int(team_info.goalkeeper))
            base_pose = self._rule_kickoff_pose(field_player_rank, has_kickoff_rights)
        return self._transform_team_pose(base_pose, team_index)

    def _transform_team_pose(self, pose: tuple[float, float, float], team_index: int) -> tuple[float, float, float]:
        x, y, theta = pose
        if team_index == 1:
            return (-x, -y, self._wrap_angle(theta + math.pi))
        return (x, y, self._wrap_angle(theta))

    def _get_waiting_pose(
        self,
        team: str,
        player_id: int,
        role: int,
        count: int,
        team_index: int | None = None,
    ) -> tuple[float, float, float]:
        half_l = self._field_l / 2
        half_w = self._field_w / 2
        line_margin = max(0.05, _DEFAULT_TOUCHLINE_WAIT_MARGIN)

        # All robots are placed on the bottom (−y) touchline, facing inward
        y = -(half_w - line_margin)
        theta = math.pi / 2.0

        # team_index=0 → left side (−x), team_index=1 → right side (+x)
        # If team_index is not provided: ally=right, opponent=left by default
        if team_index is None:
            own_right = (team == "ally")
        else:
            own_right = (team_index == 1)

        slot_index = 0 if role == 2 else min(max(1, player_id - 1), max(1, count - 1))
        x_offset = 1.35 + (slot_index * 1.45)
        x_offset = min(x_offset, half_l - 0.8)
        x = half_l - x_offset if own_right else -half_l + x_offset
        return (x, y, theta)

    def _apply_static_pose(self, agent: AgentState, x: float, y: float, theta: float) -> None:
        agent.x = x
        agent.y = y
        agent.theta = self._wrap_angle(theta)
        agent.target_x = x
        agent.target_y = y
        agent.action = 0
        agent.kick_latched = False
        agent.vel_x = 0.0
        agent.vel_y = 0.0
        self._sync_agent_action_state(agent)
        self._clamp_agent(agent)

    def _field_player_rank(self, agent: AgentState, goalkeeper_id: int) -> int:
        group = self._robots if agent.team == "ally" else self._opponents
        field_player_ids = sorted(
            other.player_id
            for other in group
            if other.player_id != goalkeeper_id
        )
        if agent.player_id not in field_player_ids:
            return 0
        return field_player_ids.index(agent.player_id)

    def _rule_goalkeeper_pose(self) -> tuple[float, float, float]:
        half_l = self._field_l / 2
        keeper_x = -half_l + self._goal_area_depth + _DEFAULT_GOALKEEPER_SET_MARGIN
        return (keeper_x, 0.0, 0.0)

    def _get_kickoff_staging_pose(self, agent: AgentState, gc: ExternalGcState) -> tuple[float, float, float]:
        """INITIAL/STANDBY only: place the kickoff team at bottom-left, non-kickoff team at bottom-right."""
        if agent.team == "ally":
            team_info = gc.msg.teams[gc.team_index]
            team_number = int(team_info.team_number)
        else:
            team_info = gc.msg.teams[gc.opponent_team_index]
            team_number = int(team_info.team_number)

        has_kickoff = int(gc.msg.kicking_team) == team_number
        # Kickoff team → left side (team_index=0), non-kickoff team → right side (team_index=1)
        staging_side = 0 if has_kickoff else 1
        count = self._num_robots if agent.team == "ally" else self._num_opponents
        return self._get_waiting_pose(agent.team, agent.player_id, int(agent.role), count, team_index=staging_side)

    def _rule_kickoff_pose(self, field_player_rank: int, has_kickoff_rights: bool) -> tuple[float, float, float]:
        safe_circle_r = self._center_circle_radius + self._center_circle_margin
        kickoff_x = -max(0.55, self._center_circle_radius * 0.5)
        support_x = -(safe_circle_r + 0.55)
        deep_support_x = support_x - 0.85
        wide_support_x = deep_support_x - 0.9
        support_y = max(1.0, min(self._field_w * 0.2, self._center_circle_radius * 1.1))
        wide_support_y = max(support_y + 0.45, min(self._field_w * 0.28, support_y + 0.65))

        if has_kickoff_rights:
            slots = [
                (kickoff_x, 0.0, 0.0),
                (support_x, support_y, 0.0),
                (deep_support_x, -support_y, 0.0),
                (wide_support_x, wide_support_y, 0.0),
                (wide_support_x, -wide_support_y, 0.0),
                (deep_support_x - 0.6, 0.0, 0.0),
            ]
        else:
            slots = [
                (support_x, max(0.8, support_y * 0.6), 0.0),
                (deep_support_x, -support_y, 0.0),
                (wide_support_x, wide_support_y - 0.2, 0.0),
                (wide_support_x, -(wide_support_y - 0.2), 0.0),
                (deep_support_x - 0.6, 0.0, 0.0),
                (deep_support_x - 1.0, support_y * 0.55, 0.0),
            ]
        return slots[min(field_player_rank, len(slots) - 1)]

    def _team_goal_points(self, team_index: int) -> tuple[tuple[float, float], tuple[float, float]]:
        goal_x = self._field_l / 2 - 0.55
        if team_index == 1:
            return ((goal_x, 0.0), (-goal_x, 0.0))
        return ((-goal_x, 0.0), (goal_x, 0.0))

    def _clamp_point(self, x: float, y: float, margin: float = 0.35) -> tuple[float, float]:
        half_l = self._field_l / 2 - margin
        half_w = self._field_w / 2 - margin
        return (
            max(-half_l, min(half_l, x)),
            max(-half_w, min(half_w, y)),
        )

    def _robot_field_extent(self, margin: float = 0.35) -> tuple[float, float]:
        outside_margin = max(
            self._border_strip,
            _DEFAULT_ROBOT_OUTSIDE_FIELD_MARGIN,
            _DEFAULT_KICK_CONTACT_RADIUS + self._robot_body_radius,
        )
        half_l = (self._field_l / 2) + outside_margin - margin
        half_w = (self._field_w / 2) + outside_margin - margin
        return (half_l, half_w)

    def _ball_escape_direction_from_walls(self) -> tuple[float, float] | None:
        field_half_l = self._field_l / 2
        field_half_w = self._field_w / 2
        goal_half_width = max(0.1, min(field_half_w, self._motion_cfg.goal_half_width))
        escape_x = 0.0
        escape_y = 0.0

        if abs(self._ball.x) >= field_half_l - _DEFAULT_BALL_WALL_ESCAPE_MARGIN:
            escape_x -= math.copysign(1.0, self._ball.x)
        if abs(self._ball.y) >= field_half_w - _DEFAULT_BALL_WALL_ESCAPE_MARGIN:
            escape_y -= math.copysign(1.0, self._ball.y)
        if (
            abs(self._ball.x) > field_half_l - _DEFAULT_BALL_WALL_ESCAPE_MARGIN
            and abs(self._ball.y) >= goal_half_width - _DEFAULT_BALL_WALL_ESCAPE_MARGIN
        ):
            escape_y -= math.copysign(1.0, self._ball.y)

        escape_norm = math.hypot(escape_x, escape_y)
        if escape_norm <= 1e-6:
            return None
        return (escape_x / escape_norm, escape_y / escape_norm)

    def _look_at(self, x: float, y: float, target_x: float, target_y: float, fallback_theta: float) -> float:
        dx = target_x - x
        dy = target_y - y
        if math.hypot(dx, dy) < 1e-4:
            return fallback_theta
        return math.atan2(dy, dx)

    def _team_agents(self, team: str) -> list[AgentState]:
        return self._robots if team == "ally" else self._opponents

    def _ordered_field_agents(self, group: list[AgentState], goalkeeper_id: int) -> list[AgentState]:
        active = self._active_field_agents(group, goalkeeper_id)
        return sorted(
            active,
            key=lambda agent: (self._field_player_rank(agent, goalkeeper_id), agent.player_id),
        )

    def _kickoff_attack_progress(self, team_index: int, x: float, y: float) -> float:
        del y
        return x if team_index == 0 else -x

    def _kickoff_global_target(self, team_index: int, distance_x: float) -> tuple[float, float]:
        return (distance_x, 0.0) if team_index == 0 else (-distance_x, 0.0)

    def _kickoff_phase(
        self,
        now: float,
        team_number: int,
        team_index: int,
        field_player_count: int,
        gc: ExternalGcState,
    ) -> str:
        if int(gc.msg.set_play) != _SET_PLAY_NONE:
            return "none"
        if int(gc.msg.kicking_team) != team_number:
            return "none"
        if self._kickoff_plan_completed:
            return "none"
        if self._kickoff_plan_started_at <= 0.0 or self._kickoff_plan_team_number != team_number:
            return "none"
        if (now - self._kickoff_plan_started_at) > _DEFAULT_KICKOFF_PLAN_WINDOW_SEC:
            return "none"

        progress = self._kickoff_attack_progress(team_index, self._ball.x, self._ball.y)
        if field_player_count <= 1:
            return "solo" if progress < _DEFAULT_KICKOFF_HANDOFF_PROGRESS else "none"
        if progress < _DEFAULT_KICKOFF_FIRST_TOUCH_TARGET:
            return "establish"
        if progress < _DEFAULT_KICKOFF_HANDOFF_PROGRESS:
            return "handoff"
        return "none"

    def _compute_drive_ball_command(
        self,
        agent: AgentState,
        target: tuple[float, float],
        prefer_heading: bool = True,
        allow_kick: bool = False,
    ) -> PlayCommand:
        target_x, target_y = target
        escape_dir = self._ball_escape_direction_from_walls()
        if escape_dir is not None:
            target_x, target_y = self._clamp_point(
                self._ball.x + (escape_dir[0] * _DEFAULT_BALL_WALL_ESCAPE_DISTANCE),
                self._ball.y + (escape_dir[1] * _DEFAULT_BALL_WALL_ESCAPE_DISTANCE),
            )
        goal_dx = target_x - self._ball.x
        goal_dy = target_y - self._ball.y
        goal_dist = max(1e-6, math.hypot(goal_dx, goal_dy))
        goal_dir_x = goal_dx / goal_dist
        goal_dir_y = goal_dy / goal_dist
        approach_x = self._ball.x - goal_dir_x * self._motion_cfg.ball_approach_offset
        approach_y = self._ball.y - goal_dir_y * self._motion_cfg.ball_approach_offset
        dribble_x = self._ball.x - goal_dir_x * self._motion_cfg.dribble_offset
        dribble_y = self._ball.y - goal_dir_y * self._motion_cfg.dribble_offset
        target_theta = self._look_at(dribble_x, dribble_y, target_x, target_y, agent.theta)
        distance_to_ball = self._distance_to_ball(agent)
        alignment_error_deg = self._angle_error_deg(agent.theta, target_theta)
        kick_ready_distance = max(0.32, self._motion_cfg.ball_capture_threshold + 0.12)
        dribble_ready_distance = max(
            _DEFAULT_DRIBBLE_CAPTURE_RADIUS,
            self._motion_cfg.ball_capture_threshold + self._motion_cfg.dribble_quit_threshold,
        )

        if (
            allow_kick and
            distance_to_ball <= kick_ready_distance and
            alignment_error_deg <= self._motion_cfg.goal_aim_min_angle_deg + 4.0
        ):
            return PlayCommand(
                dribble_x,
                dribble_y,
                target_theta,
                0.9,
                forced_action=3,
                prefer_heading=True,
                heading_only_angle_deg=max(
                    self._motion_cfg.goal_aim_min_angle_deg + 8.0,
                    _DEFAULT_DRIBBLE_STEER_ENTER_DEG,
                ),
            )
        if distance_to_ball <= dribble_ready_distance and alignment_error_deg <= _DEFAULT_DRIBBLE_FRONT_CONE_HALF_DEG:
            return PlayCommand(
                dribble_x,
                dribble_y,
                target_theta,
                1.1,
                forced_action=5,
                prefer_heading=prefer_heading,
                heading_only_angle_deg=_DEFAULT_DRIBBLE_HEADING_ONLY_DEG,
            )
        return PlayCommand(
            approach_x,
            approach_y,
            target_theta,
            1.25,
        )

    def _active_field_agents(self, group: list[AgentState], goalkeeper_id: int) -> list[AgentState]:
        active = [
            agent
            for agent in group
            if not agent.penalty and agent.player_id != goalkeeper_id and int(agent.role) != 2
        ]
        if active:
            return active
        active = [agent for agent in group if not agent.penalty]
        if active:
            return active
        return list(group)

    def _distance_to_ball(self, agent: AgentState) -> float:
        return math.hypot(agent.x - self._ball.x, agent.y - self._ball.y)

    def _closest_agent_to_ball(self, group: list[AgentState], goalkeeper_id: int) -> AgentState | None:
        active = self._active_field_agents(group, goalkeeper_id)
        if not active:
            return None
        min_dist = min(self._distance_to_ball(agent) for agent in active)
        candidates = [
            agent
            for agent in active
            if self._distance_to_ball(agent) <= min_dist + _DEFAULT_CHASER_CLUSTER_EPS
        ]
        return min(candidates, key=lambda agent: agent.player_id)

    def _nearest_distance_to_ball(self, group: list[AgentState], goalkeeper_id: int) -> float:
        active = self._active_field_agents(group, goalkeeper_id)
        if not active:
            return float("inf")
        return min(self._distance_to_ball(agent) for agent in active)

    def _team_controls_ball(
        self,
        team: str,
        own_group: list[AgentState],
        own_goalkeeper_id: int,
        opponent_group: list[AgentState],
        opponent_goalkeeper_id: int,
    ) -> bool:
        own_dist = self._nearest_distance_to_ball(own_group, own_goalkeeper_id)
        opponent_dist = self._nearest_distance_to_ball(opponent_group, opponent_goalkeeper_id)
        recently_touched = (
            self._ball.last_kicker_team == team and
            self._ball.last_kick_at > 0.0 and
            (time.monotonic() - self._ball.last_kick_at) < 1.2
        )
        if math.isinf(opponent_dist):
            return True
        return recently_touched or own_dist <= opponent_dist + _DEFAULT_TEAM_POSSESSION_MARGIN

    def _is_forward_supporter(
        self,
        agent: AgentState,
        group: list[AgentState],
        goalkeeper_id: int,
        chaser_id: int,
        attack_goal: tuple[float, float],
    ) -> bool:
        supporters = [
            other
            for other in self._active_field_agents(group, goalkeeper_id)
            if other.player_id != chaser_id
        ]
        if not supporters:
            return False
        if len(supporters) == 1:
            return supporters[0].player_id == agent.player_id
        forward = min(
            supporters,
            key=lambda other: (
                math.hypot(other.x - attack_goal[0], other.y - attack_goal[1]),
                other.player_id,
            ),
        )
        return forward.player_id == agent.player_id

    def _compute_goalkeeper_command(self, agent: AgentState, team_index: int) -> PlayCommand:
        goal_line_x = -self._field_l / 2 if team_index == 0 else self._field_l / 2
        dir_sign = 1.0 if team_index == 0 else -1.0
        ball_in_own_half = (self._ball.x <= 0.0) if team_index == 0 else (self._ball.x >= 0.0)

        # When the ball is in own half: dynamically adjust keeper_x based on the ball-to-goal distance ratio.
        # The closer the ball is to the center line, the more the keeper advances toward keeper_rush_offset;
        # near the goal, keeper_x stays at block_goal_offset.
        if ball_in_own_half:
            ball_dist_to_goal = abs(self._ball.x - goal_line_x)
            half_field = self._field_l / 2
            rush_ratio = min(1.0, ball_dist_to_goal / half_field)
            offset = self._motion_cfg.block_goal_offset + rush_ratio * (
                self._motion_cfg.keeper_rush_offset - self._motion_cfg.block_goal_offset
            )
        else:
            offset = self._motion_cfg.block_goal_offset

        keeper_x = goal_line_x + offset * dir_sign
        block_y = 0.0
        if ball_in_own_half:
            dx = self._ball.x - goal_line_x
            if abs(dx) > 0.01:
                block_y = self._ball.y * (keeper_x - goal_line_x) / dx
        block_y = max(-self._motion_cfg.goal_half_width, min(self._motion_cfg.goal_half_width, block_y))
        target_x, target_y = self._clamp_point(keeper_x, block_y, margin=0.55)
        if (
            abs(target_x - agent.x) <= self._motion_cfg.block_deadband and
            abs(target_y - agent.y) <= self._motion_cfg.block_deadband
        ):
            target_x = agent.x
            target_y = agent.y
        target_theta = self._look_at(target_x, target_y, self._ball.x, self._ball.y, agent.theta)
        # If the ball is close, rush in aggressively and kick
        dist_to_ball = self._distance_to_ball(agent)
        if ball_in_own_half and dist_to_ball <= _DEFAULT_KEEPER_RUSH_BALL_DIST:
            rush_theta = math.atan2(self._ball.y - agent.y, self._ball.x - agent.x)
            if dist_to_ball <= _DEFAULT_KICK_CONTACT_RADIUS:
                return PlayCommand(self._ball.x, self._ball.y, rush_theta, 1.4, forced_action=3)
            return PlayCommand(self._ball.x, self._ball.y, rush_theta, 1.4)
        if dist_to_ball <= _DEFAULT_KICK_CONTACT_RADIUS:
            return PlayCommand(target_x, target_y, target_theta, 1.1, forced_action=3)
        return PlayCommand(target_x, target_y, target_theta, 1.1)

    def _compute_support_command(
        self,
        agent: AgentState,
        attack_goal: tuple[float, float],
        own_goal: tuple[float, float],
        forward: bool,
    ) -> PlayCommand:
        ball_x = self._ball.x
        ball_y = self._ball.y
        if forward:
            dx = attack_goal[0] - ball_x
            dy = attack_goal[1] - ball_y
            dist_ball_to_goal = max(1e-6, math.hypot(dx, dy))
            ux = dx / dist_ball_to_goal
            uy = dy / dist_ball_to_goal
            fwd = min(_DEFAULT_SUPPORT_FORWARD, max(0.0, dist_ball_to_goal - 0.5))
            lat = _DEFAULT_SUPPORT_LATERAL
            reach = math.hypot(fwd, lat)
            max_reach = 0.85 * max(0.5, self._motion_cfg.pass_max_distance)
            if reach > max_reach and reach > 1e-6:
                scale = max_reach / reach
                fwd *= scale
                lat *= scale
            cross = ux * (agent.y - ball_y) - uy * (agent.x - ball_x)
            side = 1.0 if cross >= 0.0 else -1.0
            target_x = ball_x + (fwd * ux) + (lat * side * -uy)
            target_y = ball_y + (fwd * uy) + (lat * side * ux)
            target_x, target_y = self._clamp_point(
                target_x,
                target_y,
                margin=_DEFAULT_SUPPORT_FIELD_MARGIN,
            )
            target_theta = self._look_at(target_x, target_y, ball_x, ball_y, agent.theta)
            return PlayCommand(target_x, target_y, target_theta, 1.45)

        gbx = own_goal[0] - ball_x
        gby = own_goal[1] - ball_y
        gbn = math.hypot(gbx, gby)
        if gbn > 1e-6:
            behind = min(_DEFAULT_GUARD_BEHIND, gbn)
            target_x = ball_x + (gbx / gbn) * behind
            target_y = ball_y + (gby / gbn) * behind
        else:
            target_x = ball_x - _DEFAULT_GUARD_BEHIND
            target_y = ball_y
        target_x, target_y = self._clamp_point(target_x, target_y, margin=0.5)
        target_theta = self._look_at(target_x, target_y, ball_x, ball_y, agent.theta)
        return PlayCommand(target_x, target_y, target_theta, 1.25)

    def _compute_defense_position_command(
        self,
        agent: AgentState,
        own_goal: tuple[float, float],
    ) -> PlayCommand:
        dx = self._ball.x - own_goal[0]
        dy = self._ball.y - own_goal[1]
        dist_ball_to_goal = math.hypot(dx, dy)
        if dist_ball_to_goal > 1e-6:
            target_x = self._ball.x - (self._motion_cfg.defense_offset * (dx / dist_ball_to_goal))
            target_y = self._ball.y - (self._motion_cfg.defense_offset * (dy / dist_ball_to_goal))
        else:
            target_x = self._ball.x
            target_y = self._ball.y
        target_x, target_y = self._clamp_point(target_x, target_y)
        target_theta = self._look_at(target_x, target_y, self._ball.x, self._ball.y, agent.theta)
        return PlayCommand(target_x, target_y, target_theta, 1.4)

    def _compute_half_defense_command(
        self,
        agent: AgentState,
        own_goal: tuple[float, float],
    ) -> PlayCommand:
        target_x = self._ball.x + (own_goal[0] - self._ball.x) * 0.5
        target_y = self._ball.y + (own_goal[1] - self._ball.y) * 0.5
        target_x, target_y = self._clamp_point(target_x, target_y)
        target_theta = self._look_at(target_x, target_y, self._ball.x, self._ball.y, agent.theta)
        return PlayCommand(target_x, target_y, target_theta, 1.35)

    def _find_frontal_duel_opponent(
        self,
        agent: AgentState,
        goal_dir_x: float,
        goal_dir_y: float,
    ) -> tuple[AgentState, float] | None:
        opponent_group = self._opponents if agent.team == "ally" else self._robots
        side_x = -goal_dir_y
        side_y = goal_dir_x
        best: tuple[AgentState, float] | None = None
        best_key = (math.inf, math.inf)

        for opponent in opponent_group:
            if opponent.penalty or opponent.fallen:
                continue
            rel_x = opponent.x - self._ball.x
            rel_y = opponent.y - self._ball.y
            distance = math.hypot(rel_x, rel_y)
            if distance > 1.9:
                continue
            along = (rel_x * goal_dir_x) + (rel_y * goal_dir_y)
            lateral = (rel_x * side_x) + (rel_y * side_y)
            if along < -0.2 or along > 1.7:
                continue
            if abs(lateral) > 0.85:
                continue
            if not self._ball_is_in_front_of_agent(opponent, 70.0):
                continue
            key = (abs(lateral), distance)
            if key < best_key:
                best = (opponent, lateral)
                best_key = key

        return best

    def _compute_duel_bypass_command(
        self,
        agent: AgentState,
        target_x: float,
        target_y: float,
        goal_dir_x: float,
        goal_dir_y: float,
        threat_lateral: float,
    ) -> PlayCommand:
        side_x = -goal_dir_y
        side_y = goal_dir_x
        distance_to_ball = self._distance_to_ball(agent)
        side_sign = -math.copysign(1.0, threat_lateral) if abs(threat_lateral) > 0.08 else (1.0 if agent.team == "ally" else -1.0)
        side_offset = 0.95 if distance_to_ball < 1.1 else 1.2
        back_offset = 0.32
        bypass_x, bypass_y = self._clamp_point(
            self._ball.x - goal_dir_x * back_offset + side_x * side_sign * side_offset,
            self._ball.y - goal_dir_y * back_offset + side_y * side_sign * side_offset,
            margin=0.25,
        )
        del target_x, target_y
        bypass_theta = self._look_at(agent.x, agent.y, bypass_x, bypass_y, agent.theta)
        return PlayCommand(
            bypass_x,
            bypass_y,
            bypass_theta,
            1.35 if distance_to_ball < 1.1 else 1.55,
            prefer_heading=False,
        )

    def _compute_chase_command(
        self,
        agent: AgentState,
        attack_goal: tuple[float, float],
        team_has_control: bool,
        opponent_nearest_distance: float,
    ) -> PlayCommand:
        now = time.monotonic()
        target_x, target_y = attack_goal
        escape_dir = self._ball_escape_direction_from_walls()
        if escape_dir is not None:
            target_x, target_y = self._clamp_point(
                self._ball.x + (escape_dir[0] * _DEFAULT_BALL_WALL_ESCAPE_DISTANCE),
                self._ball.y + (escape_dir[1] * _DEFAULT_BALL_WALL_ESCAPE_DISTANCE),
            )
        goal_dx = target_x - self._ball.x
        goal_dy = target_y - self._ball.y
        goal_dist = max(1e-6, math.hypot(goal_dx, goal_dy))
        goal_dir_x = goal_dx / goal_dist
        goal_dir_y = goal_dy / goal_dist
        approach_x = self._ball.x - goal_dir_x * self._motion_cfg.ball_approach_offset
        approach_y = self._ball.y - goal_dir_y * self._motion_cfg.ball_approach_offset
        dribble_x = self._ball.x - goal_dir_x * self._motion_cfg.dribble_offset
        dribble_y = self._ball.y - goal_dir_y * self._motion_cfg.dribble_offset
        target_theta = self._look_at(dribble_x, dribble_y, target_x, target_y, agent.theta)
        distance_to_ball = self._distance_to_ball(agent)
        alignment_error_deg = abs(math.degrees(self._wrap_angle(target_theta - agent.theta)))
        kick_ready_distance = max(0.32, self._motion_cfg.ball_capture_threshold + 0.12)
        dribble_ready_distance = max(
            _DEFAULT_DRIBBLE_CAPTURE_RADIUS,
            self._motion_cfg.ball_capture_threshold + self._motion_cfg.dribble_quit_threshold,
        )
        contest_margin = 0.1 if not math.isinf(opponent_nearest_distance) else 0.0
        dribble_duration = (now - agent.dribble_since) if agent.dribble_since > 0.0 else 0.0
        duel_threat = self._find_frontal_duel_opponent(agent, goal_dir_x, goal_dir_y)

        if (
            duel_threat is not None
            and opponent_nearest_distance <= 1.7
            and distance_to_ball <= 1.9
        ):
            _, threat_lateral = duel_threat
            return self._compute_duel_bypass_command(
                agent,
                target_x,
                target_y,
                goal_dir_x,
                goal_dir_y,
                threat_lateral,
            )

        if (
            team_has_control and
            distance_to_ball <= kick_ready_distance and
            (
                alignment_error_deg <= self._motion_cfg.goal_aim_min_angle_deg + 2.0
                or (
                    dribble_duration >= _DEFAULT_DRIBBLE_MAX_CONTINUOUS_SEC
                    and alignment_error_deg <= self._motion_cfg.goal_aim_min_angle_deg + 10.0
                )
            )
        ):
            return PlayCommand(
                dribble_x,
                dribble_y,
                target_theta,
                0.95,
                forced_action=3,
                prefer_heading=True,
                heading_only_angle_deg=max(
                    self._motion_cfg.goal_aim_min_angle_deg + 6.0,
                    _DEFAULT_DRIBBLE_STEER_ENTER_DEG,
                ),
            )
        if distance_to_ball <= dribble_ready_distance and (
            team_has_control or distance_to_ball <= opponent_nearest_distance + contest_margin
        ):
            if alignment_error_deg <= _DEFAULT_DRIBBLE_FRONT_CONE_HALF_DEG:
                return PlayCommand(
                    dribble_x,
                    dribble_y,
                    target_theta,
                    1.15,
                    forced_action=5,
                    prefer_heading=True,
                    heading_only_angle_deg=_DEFAULT_DRIBBLE_HEADING_ONLY_DEG,
                )
            return PlayCommand(
                approach_x,
                approach_y,
                target_theta,
                1.0,
                prefer_heading=True,
                heading_only_angle_deg=_DEFAULT_DRIBBLE_STEER_ENTER_DEG,
            )
        return PlayCommand(
            approach_x,
            approach_y,
            target_theta,
            1.75,
        )

    def _update_gc_play_agent(self, agent: AgentState, dt: float, gc: ExternalGcState) -> None:
        if self._kickoff_release_pending and not self._team_has_kickoff_rights(agent, gc):
            target_x, target_y, target_theta = self._get_gc_target_pose(agent, gc)
            self._apply_static_pose(agent, target_x, target_y, target_theta)
            return
        now = time.monotonic()
        control_blocked = self._ball_control_blocked(agent.team, now)
        command = self._get_gc_play_target(agent, gc)
        self._move_agent_to_pose(
            agent,
            command.target_x,
            command.target_y,
            command.target_theta,
            dt,
            command.max_speed,
            prefer_heading=command.prefer_heading,
            heading_only_angle_deg=command.heading_only_angle_deg,
        )
        if command.forced_action is not None:
            forced_action = command.forced_action
            if forced_action in {3, 5} and control_blocked:
                forced_action = None
            elif forced_action == 3 and self._kick_cooldown_active(now):
                forced_action = 5
            if forced_action is not None:
                agent.action = forced_action
        self._sync_agent_action_state(agent)

    def _get_gc_play_target(
        self,
        agent: AgentState,
        gc: ExternalGcState,
    ) -> PlayCommand:
        now = time.monotonic()
        if agent.team == "ally":
            team_index = gc.team_index
            team_info = gc.msg.teams[gc.team_index]
            opponent_index = gc.opponent_team_index
        else:
            team_index = gc.opponent_team_index
            team_info = gc.msg.teams[gc.opponent_team_index]
            opponent_index = gc.team_index

        own_goal, attack_goal = self._team_goal_points(team_index)
        own_group = self._team_agents(agent.team)
        opponent_group = self._team_agents("opponent" if agent.team == "ally" else "ally")
        own_goalkeeper_id = int(team_info.goalkeeper)
        opponent_goalkeeper_id = int(gc.msg.teams[opponent_index].goalkeeper)
        ordered_field_agents = self._ordered_field_agents(own_group, own_goalkeeper_id)
        team_number = int(team_info.team_number)
        is_goalkeeper = agent.player_id == int(team_info.goalkeeper) or int(agent.role) == 2
        if is_goalkeeper:
            return self._compute_goalkeeper_command(agent, team_index)

        kickoff_phase = self._kickoff_phase(
            now,
            team_number,
            team_index,
            len(ordered_field_agents),
            gc,
        )
        if kickoff_phase != "none" and ordered_field_agents:
            kickoff_initiator = ordered_field_agents[0]
            kickoff_receiver = ordered_field_agents[1] if len(ordered_field_agents) >= 2 else None
            if kickoff_phase == "establish":
                if agent.player_id == kickoff_initiator.player_id:
                    return self._compute_drive_ball_command(
                        agent,
                        self._kickoff_global_target(team_index, _DEFAULT_KICKOFF_FIRST_TOUCH_TARGET),
                        prefer_heading=True,
                        allow_kick=True,
                    )
                if kickoff_receiver is not None and agent.player_id == kickoff_receiver.player_id:
                    return self._compute_support_command(agent, attack_goal, own_goal, True)
            elif kickoff_phase == "handoff":
                if kickoff_receiver is not None and agent.player_id == kickoff_receiver.player_id:
                    return self._compute_drive_ball_command(
                        agent,
                        self._kickoff_global_target(team_index, _DEFAULT_KICKOFF_SECOND_TOUCH_TARGET),
                        prefer_heading=True,
                        allow_kick=True,
                    )
                if agent.player_id == kickoff_initiator.player_id:
                    return self._compute_support_command(agent, attack_goal, own_goal, False)
            elif kickoff_phase == "solo" and agent.player_id == kickoff_initiator.player_id:
                return self._compute_drive_ball_command(
                    agent,
                    self._kickoff_global_target(team_index, _DEFAULT_KICKOFF_SECOND_TOUCH_TARGET),
                    prefer_heading=True,
                    allow_kick=True,
                )

        chaser = self._closest_agent_to_ball(own_group, own_goalkeeper_id)
        team_has_control = self._team_controls_ball(
            agent.team,
            own_group,
            own_goalkeeper_id,
            opponent_group,
            opponent_goalkeeper_id,
        )
        if self._kickoff_release_pending and self._team_has_kickoff_rights(agent, gc):
            team_has_control = True
        opponent_nearest_distance = self._nearest_distance_to_ball(opponent_group, opponent_goalkeeper_id)

        if chaser is not None and chaser.player_id == agent.player_id:
            return self._compute_chase_command(
                agent,
                attack_goal,
                team_has_control,
                opponent_nearest_distance,
            )

        supporters = [
            other
            for other in self._active_field_agents(own_group, own_goalkeeper_id)
            if chaser is None or other.player_id != chaser.player_id
        ]
        if not team_has_control:
            primary_defender = min(
                supporters,
                key=lambda other: (self._distance_to_ball(other), other.player_id),
                default=None,
            )
            if primary_defender is not None and primary_defender.player_id == agent.player_id:
                return self._compute_defense_position_command(agent, own_goal)
            return self._compute_half_defense_command(agent, own_goal)

        is_forward_support = self._is_forward_supporter(
            agent,
            own_group,
            own_goalkeeper_id,
            chaser.player_id if chaser is not None else -1,
            attack_goal,
        )
        return self._compute_support_command(agent, attack_goal, own_goal, is_forward_support)

    def _team_has_kickoff_rights(self, agent: AgentState, gc: ExternalGcState) -> bool:
        team_info = gc.msg.teams[gc.team_index] if agent.team == "ally" else gc.msg.teams[gc.opponent_team_index]
        team_number = int(team_info.team_number)
        return int(gc.msg.kicking_team) in {team_number, _KICKING_TEAM_NONE}

    def _update_kickoff_phase_locked(self, now: float, gc: ExternalGcState | None) -> None:
        if gc is None:
            self._kickoff_release_pending = False
            self._reset_kickoff_release_tracking_locked()
            self._reset_kickoff_plan_locked()
            return
        gc_mode = self._gc_motion_mode(gc)
        if gc_mode in {"ready", "set"}:
            if int(gc.msg.set_play) == _SET_PLAY_NONE:
                self._kickoff_release_pending = True
            else:
                # Non-kickoff set plays (goal kick, corner kick, etc.): release freeze immediately
                self._kickoff_release_pending = False
            self._reset_kickoff_release_tracking_locked()
            self._reset_kickoff_plan_locked()
            return
        if gc_mode != "play":
            self._kickoff_release_pending = False
            self._reset_kickoff_release_tracking_locked()
            self._reset_kickoff_plan_locked()
            return
        if int(gc.msg.set_play) == _SET_PLAY_NONE and int(gc.msg.kicking_team) != _KICKING_TEAM_NONE:
            if not self._kickoff_plan_completed:
                if (
                    self._kickoff_plan_started_at <= 0.0 or
                    self._kickoff_plan_team_number != int(gc.msg.kicking_team)
                ):
                    self._kickoff_plan_started_at = now
                    self._kickoff_plan_team_number = int(gc.msg.kicking_team)
                active_team_index = gc.team_index if int(gc.msg.kicking_team) == self._team_number else gc.opponent_team_index
                progress = self._kickoff_attack_progress(active_team_index, self._ball.x, self._ball.y)
                if (
                    (now - self._kickoff_plan_started_at) > _DEFAULT_KICKOFF_PLAN_WINDOW_SEC or
                    progress >= _DEFAULT_KICKOFF_HANDOFF_PROGRESS
                ):
                    self._complete_kickoff_plan_locked()
        else:
            self._reset_kickoff_plan_locked()
        if not self._kickoff_release_pending:
            return
        if int(gc.msg.kicking_team) == _KICKING_TEAM_NONE:
            self._kickoff_release_pending = False
            self._reset_kickoff_release_tracking_locked()
            return
        if self._kickoff_release_started_at <= 0.0:
            self._kickoff_release_started_at = now
        if not self._kickoff_release_origin_fixed:
            self._kickoff_release_origin_x = self._ball.x
            self._kickoff_release_origin_y = self._ball.y
            self._kickoff_release_origin_fixed = True
        ball_moved = math.hypot(
            self._ball.x - self._kickoff_release_origin_x,
            self._ball.y - self._kickoff_release_origin_y,
        ) > _DEFAULT_WAIT_BALL_MOVE_THRESHOLD
        if ball_moved or (now - self._kickoff_release_started_at) >= _DEFAULT_WAIT_BALL_MOVE_TIMEOUT_SEC:
            self._kickoff_release_pending = False
            self._reset_kickoff_release_tracking_locked()

    def _update_manual_agent(self, agent: AgentState, dt: float) -> None:
        linear_speed = 1.8
        angular_speed = 2.4
        agent.x += self._manual_vx * linear_speed * dt
        agent.y += self._manual_vy * linear_speed * dt
        agent.theta = self._wrap_angle(agent.theta + self._manual_omega * angular_speed * dt)
        agent.orbit_angle = math.atan2(agent.y - agent.orbit_cy, agent.x - agent.orbit_cx)
        agent.target_x = agent.x + self._manual_vx * 0.7
        agent.target_y = agent.y + self._manual_vy * 0.7
        agent.vel_x = self._manual_vx * linear_speed
        agent.vel_y = self._manual_vy * linear_speed
        self._clamp_agent(agent)
        self._update_action(agent, manual=True)

    def _update_action(self, agent: AgentState, manual: bool) -> None:
        if manual:
            moving = abs(self._manual_vx) > 0.05 or abs(self._manual_vy) > 0.05
            turning = abs(self._manual_omega) > 0.05
            if moving:
                agent.action = 1
            elif turning:
                agent.action = 2
            else:
                agent.action = 0
            self._sync_agent_action_state(agent)
            return
        if math.hypot(agent.x - self._ball.x, agent.y - self._ball.y) < 0.55:
            if self._ball_control_blocked(agent.team):
                agent.action = 1
            else:
                agent.action = 5 if self._kick_cooldown_active() else 3
        else:
            agent.action = 1
        self._sync_agent_action_state(agent)

    def _clamp_agent(self, agent: AgentState) -> None:
        margin = max(0.3, self._robot_body_radius)
        half_l, half_w = self._robot_field_extent(margin=margin)
        if agent.x < -half_l:
            agent.x = -half_l
            agent.vel_x = max(0.0, agent.vel_x)
        elif agent.x > half_l:
            agent.x = half_l
            agent.vel_x = min(0.0, agent.vel_x)
        if agent.y < -half_w:
            agent.y = -half_w
            agent.vel_y = max(0.0, agent.vel_y)
        elif agent.y > half_w:
            agent.y = half_w
            agent.vel_y = min(0.0, agent.vel_y)
        agent.theta = self._wrap_angle(agent.theta)

    def _build_udp_packets(self, snapshot: dict) -> list[tuple[bytes, tuple[str, int]]]:
        all_robots = snapshot["robots"]
        selected_ids = set(snapshot["legacy"]["robot_ids"])
        robots = [r for r in all_robots if r["player_id"] in selected_ids]
        ball = snapshot["ball"]
        manual = snapshot["manual"]
        goal_x = snapshot["field"]["length"] / 2 - 0.2
        perceived = snapshot["perceived"]
        packets: list[tuple[bytes, tuple[str, int]]] = []
        addr = (self._inet_addr, self._port)

        for robot in robots:
            perc = perceived.get(robot["player_id"])
            px = perc["x"] if perc else robot["x"]
            py = perc["y"] if perc else robot["y"]
            ptheta = perc["theta"] if perc else robot["theta"]
            pbx = (perc["ball_x"] if perc.get("ball_x") is not None else ball["x"]) if perc else ball["x"]
            pby = (perc["ball_y"] if perc.get("ball_y") is not None else ball["y"]) if perc else ball["y"]

            # FOV-filtered allies/opponents (already noisy from _build_perceived_locked)
            perc_allies = perc.get("allies", []) if perc else []
            perc_opps = perc.get("opponents", []) if perc else []

            dist_ball = math.hypot(px - pbx, py - pby)
            if manual["enabled"] and manual["team"] == "ally" and manual["id"] == robot["player_id"]:
                wcmd_x = robot["target_x"]
                wcmd_y = robot["target_y"]
            else:
                wcmd_x = pbx if dist_ball > 0.6 else robot["target_x"]
                wcmd_y = pby if dist_ball > 0.6 else robot["target_y"]
            kick_target_x = goal_x
            kick_target_y = 0.0

            # Use FOV-filtered opponent positions (already noisy)
            noisy_opponents = [(o["x"], o["y"]) for o in perc_opps]

            def ally_slot(slot: int) -> tuple[int, float, float, float]:
                if slot >= len(perc_allies):
                    return (0, 0.0, 0.0, 0.0)
                a = perc_allies[slot]
                other = next((r for r in all_robots if r["player_id"] == a["id"]), None)
                if other is None:
                    return (0, 0.0, 0.0, 0.0)
                return (int(a["id"]), float(a["x"]), float(a["y"]), float(other["theta"]))

            def enemy_slot(slot: int) -> tuple[int, float, float, float]:
                if slot >= len(noisy_opponents):
                    return (0, 0.0, 0.0, 0.0)
                ex, ey = noisy_opponents[slot]
                return (0, ex, ey, 0.0)

            oa1 = ally_slot(0)
            oa2 = ally_slot(1)
            or1 = enemy_slot(0)
            or2 = enemy_slot(1)
            or3 = enemy_slot(2)
            fused_enemy_count = min(len(perc_opps), _MAX_OPPONENTS)

            pkt = _MSG_STRUCT.pack(
                int(robot["player_id"]),
                px, py, ptheta,
                px, py, ptheta,
                px, py, ptheta,
                px, py, ptheta,
                1,
                float(robot["eval_mc"]), 0.78,
                wcmd_x, wcmd_y, ptheta,
                kick_target_x, kick_target_y,
                pbx, pby,
                ball["vx"], ball["vy"],
                0.02, 0.0, 0.0, 0.02,
                0.04, 0.0, 0.0, 0.04,
                pbx, pby,
                oa1[0], oa1[1], oa1[2], oa1[3],
                0.02, 0.02, 0.04,
                oa2[0], oa2[1], oa2[2], oa2[3],
                0.02, 0.02, 0.04,
                or1[0], or1[1], or1[2], or1[3],
                or2[0], or2[1], or2[2], or2[3],
                or3[0], or3[1], or3[2], or3[3],
                0,
                True,
                True,
                bool(robot["penalty"]),
                0.0, 0.0, 0.0,
                0.05, 0.05, 0.02,
                0.05, 0.05, 0.02,
                0.08, 0.08, 0.03,
                int(robot["action"]),
                max(1, len(all_robots)),
                pbx, pby,
                fused_enemy_count,
                noisy_opponents[0][0] if fused_enemy_count > 0 else 0.0,
                noisy_opponents[0][1] if fused_enemy_count > 0 else 0.0,
                1 if fused_enemy_count > 0 else 0,
                noisy_opponents[1][0] if fused_enemy_count > 1 else 0.0,
                noisy_opponents[1][1] if fused_enemy_count > 1 else 0.0,
                1 if fused_enemy_count > 1 else 0,
                noisy_opponents[2][0] if fused_enemy_count > 2 else 0.0,
                noisy_opponents[2][1] if fused_enemy_count > 2 else 0.0,
                1 if fused_enemy_count > 2 else 0,
                int(robot["role"]),
                10 if robot["penalty"] else 0,
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            )
            packets.append((pkt, addr))
        return packets

    def _robot_stamp(self, robot_id: int, base_ns: int):
        """Return a per-robot builtin_interfaces.msg.Time with startup offset + small jitter."""
        from builtin_interfaces.msg import Time as RosTime
        offset_ns = self._robot_startup_offset_ns.get(robot_id, 0)
        jitter_ns = int(random.gauss(0, 5_000_000))  # ±5 ms Gaussian jitter
        ns = max(0, base_ns + offset_ns + jitter_ns)
        t = RosTime()
        t.sec = ns // 1_000_000_000
        t.nanosec = ns % 1_000_000_000
        return t

    def _publish_legacy_snapshot(self, snapshot: dict) -> None:
        robot_ids = snapshot["legacy"]["robot_ids"]
        if not robot_ids:
            return
        base_ns = self.get_clock().now().nanoseconds
        with self._lock:
            gc_state = self._clone_external_gc_locked(time.monotonic())
        all_robots = snapshot["robots"]
        opponents = snapshot["opponents"]
        goal_x = snapshot["field"]["length"] / 2 - 0.2
        primary_id = robot_ids[0]

        for robot_id in robot_ids:
            source = next((r for r in all_robots if r["player_id"] == robot_id), None)
            if source is None:
                continue
            stamp = self._robot_stamp(robot_id, base_ns)
            perc = snapshot["perceived"].get(robot_id)
            per_pubs = self._pubs_per_robot.get(robot_id, {})
            if per_pubs:
                self._publish_one_robot_legacy(
                    per_pubs, stamp, source, perc, all_robots, opponents, gc_state, goal_x, snapshot)
            if robot_id == primary_id and self._pubs:
                self._publish_one_robot_legacy(
                    self._pubs, stamp, source, perc, all_robots, opponents, gc_state, goal_x, snapshot)

    def _publish_one_robot_legacy(
        self, pubs: dict, stamp, source: dict, perc: dict | None,
        all_robots: list, opponents: list, gc_state, goal_x: float, snapshot: dict,
    ) -> None:
        sx = perc["x"] if perc else source["x"]
        sy = perc["y"] if perc else source["y"]
        stheta = perc["theta"] if perc else source["theta"]
        perc_source = {**source, "x": sx, "y": sy, "theta": stheta}
        ball = snapshot["ball"]
        ball_in_fov = perc.get("ball_in_fov", False) if perc else False
        bx = perc["ball_x"] if (perc and perc.get("ball_x") is not None) else ball["x"]
        by = perc["ball_y"] if (perc and perc.get("ball_y") is not None) else ball["y"]
        bvx = perc["ball_vx"] if (perc and perc.get("ball_vx") is not None) else ball["vx"]
        bvy = perc["ball_vy"] if (perc and perc.get("ball_vy") is not None) else ball["vy"]
        perc_ball = {**ball, "x": bx, "y": by, "vx": bvx, "vy": bvy}

        if perc:
            visible_opp_ids = {o["id"] for o in perc.get("opponents", [])}
            visible_ally_ids = {a["id"] for a in perc.get("allies", [])}
            perc_opponents = [
                {**o,
                 "x": self._apply_noise(o["x"], self._noise_other_robot),
                 "y": self._apply_noise(o["y"], self._noise_other_robot)}
                for o in opponents if o["player_id"] in visible_opp_ids
            ]
            perc_allies = [
                {**r,
                 "x": self._apply_noise(r["x"], self._noise_other_robot),
                 "y": self._apply_noise(r["y"], self._noise_other_robot)}
                for r in all_robots if r["player_id"] in visible_ally_ids
            ]
        else:
            perc_opponents = []
            perc_allies = []

        pubs["local_pose"].publish(self._make_pose2d(sx, sy, stheta))
        pubs["destination"].publish(self._make_pose2d(source["target_x"], source["target_y"], stheta))
        pubs["pass_target"].publish(self._make_pose2d(goal_x, 0.0, 0.0))
        pubs["detected_objects"].publish(self._make_detected_objects(
            stamp, perc_source, perc_ball, perc_opponents, perc_allies, ball_in_fov))
        pubs["pass_sequence"].publish(Int16(data=0))
        pubs["bt_node"].publish(String(data=_ACTION_TO_BT.get(int(source["action"]), "StopMove")))
        if not (self._publish_gc_ros_topics and self._direct_gc_udp_active()):
            pubs["game"].publish(
                self._make_gc_msg(
                    player_id=source["player_id"],
                    robots=all_robots,
                    opponents=opponents,
                    gc_state=gc_state,
                ),
            )
        pubs["lifted"].publish(Bool(data=bool(source.get("fallen", False))))
        pubs["result_cov"].publish(self._make_pose_cov(stamp, perc_source, 0.05, 0.05, 0.03))
        pubs["fused_enemies"].publish(self._make_fused_enemies(stamp, perc_opponents))
        pubs["rl_vel_cmd"].publish(self._make_rl_vel_cmd(source))
        for robot in all_robots:
            if robot["player_id"] != source["player_id"]:
                rperc = snapshot["perceived"].get(robot["player_id"])
                pubs["udp_data"].publish(self._make_udp_data(stamp, robot, ball, rperc))

    def _make_pose2d(self, x: float, y: float, theta: float) -> Pose2D:
        msg = Pose2D()
        msg.x = float(x)
        msg.y = float(y)
        msg.theta = float(theta)
        return msg

    def _make_rl_vel_cmd(self, source: dict) -> Float64MultiArray:
        vx_world = float(source.get("vel_x", 0.0))
        vy_world = float(source.get("vel_y", 0.0))
        theta = float(source.get("theta", 0.0))
        c = math.cos(theta)
        s = math.sin(theta)
        vx_local = (c * vx_world) + (s * vy_world)
        vy_local = (-s * vx_world) + (c * vy_world)

        wz = 0.0
        if not bool(source.get("fallen", False)) and not bool(source.get("penalty", False)):
            target_x = float(source.get("target_x", source.get("x", 0.0)))
            target_y = float(source.get("target_y", source.get("y", 0.0)))
            dx = target_x - float(source.get("x", 0.0))
            dy = target_y - float(source.get("y", 0.0))
            if math.hypot(dx, dy) > 0.05:
                desired_theta = math.atan2(dy, dx)
                yaw_error = self._wrap_angle(desired_theta - theta)
                wz = max(-2.8, min(2.8, yaw_error * 2.0))

        msg = Float64MultiArray()
        msg.data = [vx_local, vy_local, wz]
        return msg

    def _make_pose_cov(self, stamp, source: dict, sx: float, sy: float, st: float) -> PoseWithCovarianceStamped:
        msg = PoseWithCovarianceStamped()
        msg.header.stamp = stamp
        msg.header.frame_id = "map"
        msg.pose.pose.position.x = float(source["x"])
        msg.pose.pose.position.y = float(source["y"])
        msg.pose.pose.orientation.z = math.sin(source["theta"] / 2.0)
        msg.pose.pose.orientation.w = math.cos(source["theta"] / 2.0)
        msg.pose.covariance[0] = sx * sx
        msg.pose.covariance[7] = sy * sy
        msg.pose.covariance[35] = st * st
        return msg

    def _make_detected_objects(
        self, stamp, source: dict, ball: dict, opponents: list[dict], allies: list[dict],
        ball_in_fov: bool = True,
    ) -> FoundObjectArray:
        msg = FoundObjectArray()
        msg.header.stamp = stamp
        objects: list[FoundObject] = []

        if ball_in_fov:
            ball_local_x, ball_local_y = self._to_local(source, ball["x"], ball["y"])
            ball_obj = FoundObject()
            ball_obj.name = "ball"
            ball_obj.id = 0
            ball_obj.pos.x = float(ball_local_x)
            ball_obj.pos.y = float(ball_local_y)
            ball_obj.velocity.x = float(ball["vx"])
            ball_obj.velocity.y = float(ball["vy"])
            ball_obj.score = 1.0
            objects.append(ball_obj)

        for idx, opponent in enumerate(opponents[:_MAX_OPPONENTS], start=1):
            ox, oy = self._to_local(source, opponent["x"], opponent["y"])
            obj = FoundObject()
            obj.name = "robot"
            obj.id = idx
            obj.pos.x = float(ox)
            obj.pos.y = float(oy)
            obj.score = 0.9
            objects.append(obj)

        for ally in allies:
            if ally["player_id"] == source["player_id"]:
                continue
            ax, ay = self._to_local(source, ally["x"], ally["y"])
            obj = FoundObject()
            obj.name = "ally"
            obj.id = int(ally["player_id"])
            obj.pos.x = float(ax)
            obj.pos.y = float(ay)
            obj.score = 0.9
            objects.append(obj)

        msg.data = objects
        msg.length = len(objects)
        return msg

    def _make_gc_msg(
        self,
        player_id: int,
        robots: list[dict],
        opponents: list[dict],
        gc_state: ExternalGcState | None = None,
    ) -> RoboCupGameControlRosData:
        if gc_state is not None:
            msg = copy.deepcopy(gc_state.msg)
            msg.team_index = int(gc_state.team_index)
            msg.robot_index = max(0, min(19, player_id - 1))
            return msg

        msg = RoboCupGameControlRosData()
        msg.header = "sim"
        msg.version = 1
        msg.packet_number = self._gc_packet_number % 255
        self._gc_packet_number += 1
        msg.players_per_team = max(len(robots), len(opponents), 1)
        msg.competition_type = 0
        msg.stopped = 0
        msg.game_phase = 0
        msg.state = _STATE_PLAYING
        msg.set_play = _SET_PLAY_NONE
        msg.first_half = 1
        msg.kicking_team = self._team_number
        msg.secs_remaining = 600
        msg.secondary_time = 0
        msg.teams = [
            self._make_gc_team(self._team_number, robots),
            self._make_gc_team(self._opponent_team_number, opponents),
        ]
        msg.secondary_state = 0
        msg.secondary_state_info = [0, 0, 0, 0]
        msg.kick_off_team = self._team_number
        msg.team_index = 0
        msg.robot_index = player_id - 1
        return msg

    def _make_gc_team(self, team_number: int, players: list[dict]) -> TeamRosInfo:
        msg = TeamRosInfo()
        msg.team_number = team_number
        msg.goalkeeper = 1 if not players else next(
            (int(p["player_id"]) for p in players if int(p["role"]) == 2),
            1,
        )
        msg.score = 0
        msg.players = [RobotRosInfo() for _ in range(20)]
        for index, player in enumerate(players[:20]):
            info = msg.players[index]
            info.penalty = _PENALTY_SIM if player["penalty"] else _PENALTY_NONE
            info.secs_till_unpenalised = 10 if player["penalty"] else 0
            info.cautions = 0
        return msg

    def _make_udp_data(self, stamp, robot: dict, ball: dict, perc: dict | None = None) -> RoboCupRobotData:
        msg = RoboCupRobotData()
        msg.header.stamp = stamp

        msg.state.data = str(robot["action"])

        rx = perc["x"] if perc else robot["x"]
        ry = perc["y"] if perc else robot["y"]
        rtheta = perc["theta"] if perc else robot["theta"]
        bx = (perc["ball_x"] if perc.get("ball_x") is not None else ball["x"]) if perc else ball["x"]
        by = (perc["ball_y"] if perc.get("ball_y") is not None else ball["y"]) if perc else ball["y"]
        bvx = (perc["ball_vx"] if perc.get("ball_vx") is not None else ball["vx"]) if perc else ball["vx"]
        bvy = (perc["ball_vy"] if perc.get("ball_vy") is not None else ball["vy"]) if perc else ball["vy"]

        msg.current_pose.player_id = int(robot["player_id"])
        msg.current_pose.position = self._make_pose2d(rx, ry, rtheta)
        msg.current_pose.covariance[0] = 0.04
        msg.current_pose.covariance[7] = 0.04
        msg.current_pose.covariance[35] = 0.05

        msg.target_pose.player_id = 0
        msg.target_pose.position = self._make_pose2d(robot["target_x"], robot["target_y"], 0.0)

        ball_data = ProtoBufBallData()
        ball_data.position = self._make_pose2d(bx, by, 0.0)
        ball_data.velocity = self._make_pose2d(bvx, bvy, 0.0)
        ball_data.detected.data = True
        ball_data.covariance[0] = 0.03
        ball_data.covariance[7] = 0.03
        msg.ball = ball_data

        msg.pass_sequence.data = 0
        msg.penalty.data = bool(robot["penalty"])
        return msg

    def _make_fused_enemies(self, stamp, opponents: list[dict]) -> ObservedRobotArray:
        msg = ObservedRobotArray()
        msg.header.stamp = stamp
        msg.observer_id = 0
        observations: list[ProtoBufRobotData] = []
        num_sources: list[int] = []
        for opponent in opponents[:_MAX_OPPONENTS]:
            item = ProtoBufRobotData()
            item.player_id = 0
            item.position = self._make_pose2d(opponent["x"], opponent["y"], opponent["theta"])
            item.covariance[0] = 0.03
            item.covariance[7] = 0.03
            item.covariance[35] = 0.06
            observations.append(item)
            num_sources.append(1)
        msg.observations = observations
        msg.observation_num_sources = num_sources
        return msg

    def _to_local(self, source: dict, target_x: float, target_y: float) -> tuple[float, float]:
        dx = target_x - source["x"]
        dy = target_y - source["y"]
        c = math.cos(source["theta"])
        s = math.sin(source["theta"])
        return (c * dx + s * dy, -s * dx + c * dy)

    @staticmethod
    def _wrap_angle(theta: float) -> float:
        return math.atan2(math.sin(theta), math.cos(theta))

    def _apply_noise(self, value: float, sigma: float) -> float:
        if not self._noise_enabled or sigma <= 0.0:
            return value
        return value + random.gauss(0.0, sigma)

    def _build_perceived_locked(self) -> dict[int, dict]:
        perceived: dict[int, dict] = {}
        for robot in self._robots:
            ball_in_fov = self._in_fov(robot, self._ball.x, self._ball.y)
            perceived[robot.player_id] = {
                "x": self._apply_noise(robot.x, self._noise_self_pos),
                "y": self._apply_noise(robot.y, self._noise_self_pos),
                "theta": self._apply_noise(robot.theta, self._noise_self_angle),
                "ball_x": self._apply_noise(self._ball.x, self._noise_ball) if ball_in_fov else None,
                "ball_y": self._apply_noise(self._ball.y, self._noise_ball) if ball_in_fov else None,
                "ball_vx": self._ball.vx if ball_in_fov else None,
                "ball_vy": self._ball.vy if ball_in_fov else None,
                "ball_in_fov": ball_in_fov,
                "allies": [
                    {
                        "id": other.player_id,
                        "x": self._apply_noise(other.x, self._noise_other_robot),
                        "y": self._apply_noise(other.y, self._noise_other_robot),
                    }
                    for other in self._robots
                    if other.player_id != robot.player_id
                    and self._in_fov(robot, other.x, other.y)
                ],
                "opponents": [
                    {
                        "id": opp.player_id,
                        "x": self._apply_noise(opp.x, self._noise_other_robot),
                        "y": self._apply_noise(opp.y, self._noise_other_robot),
                    }
                    for opp in self._opponents
                    if self._in_fov(robot, opp.x, opp.y)
                ],
            }
        return perceived

    def set_noise(
        self,
        enabled: bool | None = None,
        show_in_gui: bool | None = None,
        self_pos: float | None = None,
        self_angle: float | None = None,
        ball: float | None = None,
        other_robot: float | None = None,
    ) -> None:
        with self._lock:
            if enabled is not None:
                self._noise_enabled = bool(enabled)
            if show_in_gui is not None:
                self._noise_show_in_gui = bool(show_in_gui)
            if self_pos is not None:
                self._noise_self_pos = max(0.0, float(self_pos))
            if self_angle is not None:
                self._noise_self_angle = max(0.0, float(self_angle))
            if ball is not None:
                self._noise_ball = max(0.0, float(ball))
            if other_robot is not None:
                self._noise_other_robot = max(0.0, float(other_robot))

    def set_fall(
        self,
        fall_prob: float | None = None,
        recovery_sec: float | None = None,
    ) -> None:
        with self._lock:
            if fall_prob is not None:
                self._fall_prob = max(0.0, min(1.0, float(fall_prob)))
            if recovery_sec is not None:
                self._fall_recovery_sec = max(1.0, float(recovery_sec))

    def set_fov(
        self,
        angle_deg: float | None = None,
        range_m: float | None = None,
    ) -> None:
        with self._lock:
            if angle_deg is not None:
                self._fov_angle_deg = max(1.0, min(360.0, float(angle_deg)))
            if range_m is not None:
                self._fov_range_m = max(0.1, float(range_m))

    def _update_falls_locked(
        self,
        now: float,
        contact_pairs: list[tuple[AgentState, AgentState, float]] | None = None,
    ) -> None:
        for agent in (*self._robots, *self._opponents):
            if agent.fallen:
                if now - agent.fallen_at >= self._fall_recovery_sec:
                    agent.fallen = False
                    agent.fallen_at = 0.0
        if not contact_pairs or self._fall_prob <= 0.0:
            return

        min_distance = self._robot_body_radius * 2.0
        contact_span = max(1e-6, self._robot_contact_distance - min_distance)
        for first, second, distance in contact_pairs:
            if first.fallen or second.fallen or first.penalty or second.penalty:
                continue
            if distance >= self._robot_contact_distance:
                continue

            if distance <= min_distance:
                closeness = 1.0
            else:
                closeness = (self._robot_contact_distance - distance) / contact_span
            fall_chance = self._fall_prob * max(0.0, min(1.0, closeness))
            if random.random() >= fall_chance:
                continue

            first_speed = math.hypot(first.vel_x, first.vel_y)
            second_speed = math.hypot(second.vel_x, second.vel_y)
            if abs(first_speed - second_speed) <= 0.1:
                victim = first if random.random() < 0.5 else second
            else:
                victim = first if first_speed > second_speed else second
            self._set_agent_fallen(victim, now)

    def _in_fov(self, robot: AgentState, px: float, py: float) -> bool:
        dx = px - robot.x
        dy = py - robot.y
        if math.hypot(dx, dy) > self._fov_range_m:
            return False
        bearing = math.atan2(dy, dx)
        return abs(self._wrap_angle(bearing - robot.theta)) <= math.radians(self._fov_angle_deg / 2.0)


def _resolve_static_dir() -> Path:
    """Prefer the src path (hot-reload during development); fall back to share/ if not found."""
    src = Path(__file__).parent / "static"
    if (src / "index.html").exists():
        return src
    return Path(get_package_share_directory("robocup_match_2d_simulation")) / "static"


def create_app(sim: StrategyGuiSim) -> FastAPI:
    from fastapi.responses import FileResponse

    app = FastAPI(title="RoboCup Sim 2D")
    static_dir = _resolve_static_dir()

    class _NoCacheMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            path = request.url.path
            if path == "/" or path.startswith("/static/") or path.endswith(".html"):
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            return response

    app.add_middleware(_NoCacheMiddleware)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(static_dir / "index.html"))

    @app.get("/api/state")
    async def get_state():
        return JSONResponse(sim.get_state())

    @app.post("/api/robot/{pid}/pose")
    async def set_robot_pose(pid: int, body: PoseBody):
        return {"ok": sim.override_agent("ally", pid, body.x, body.y, body.theta)}

    @app.post("/api/opponent/{pid}/pose")
    async def set_opponent_pose(pid: int, body: PoseBody):
        return {"ok": sim.override_agent("opponent", pid, body.x, body.y, body.theta)}

    @app.post("/api/ball/pose")
    async def set_ball_pose(body: BallBody):
        sim.override_ball(body.x, body.y)
        return {"ok": True}

    @app.post("/api/manual/select")
    async def select_manual_target(body: ManualSelectBody):
        ok = sim.set_manual_target(body.team, body.id, body.enabled)
        if not ok:
            return JSONResponse({"ok": False, "error": "invalid manual target"}, status_code=400)
        return {"ok": True}

    @app.post("/api/manual/input")
    async def set_manual_input(body: ManualInputBody):
        sim.set_manual_command(body.vx, body.vy, body.omega)
        return {"ok": True}

    @app.post("/api/legacy/robot_id")
    async def set_legacy_robot_id(body: LegacyRobotIdBody):
        ok = sim.set_legacy_robot_id(body.robot_id)
        if not ok:
            return JSONResponse({"ok": False, "error": f"invalid robot_id: {body.robot_id}"}, status_code=400)
        return {"ok": True}

    @app.post("/api/legacy/robot_ids")
    async def set_legacy_robot_ids(body: LegacyRobotIdsBody):
        ok = sim.set_legacy_robot_ids(body.robot_ids)
        if not ok:
            return JSONResponse({"ok": False, "error": f"invalid robot_ids: {body.robot_ids}"}, status_code=400)
        return {"ok": True}

    @app.post("/api/noise")
    async def set_noise(body: NoiseBody):
        sim.set_noise(
            enabled=body.enabled,
            show_in_gui=body.show_in_gui,
            self_pos=body.self_pos,
            self_angle=body.self_angle,
            ball=body.ball,
            other_robot=body.other_robot,
        )
        return {"ok": True}

    @app.post("/api/fall")
    async def set_fall(body: FallBody):
        sim.set_fall(
            fall_prob=body.fall_prob,
            recovery_sec=body.recovery_sec,
        )
        return {"ok": True}

    @app.post("/api/fov")
    async def set_fov(body: FovBody):
        sim.set_fov(
            angle_deg=body.angle_deg,
            range_m=body.range_m,
        )
        return {"ok": True}

    @app.post("/api/control")
    async def control(body: ControlBody):
        action = body.action
        if action == "pause":
            sim.set_paused(True)
        elif action == "resume":
            sim.set_paused(False)
        elif action == "reset":
            sim.reset()
        elif action == "set_speed":
            sim.set_speed(body.value)
        else:
            return JSONResponse({"ok": False, "error": f"unknown action: {action}"}, status_code=400)
        return {"ok": True, "action": action}

    return app


def main(args=None) -> None:
    rclpy.init(args=args)
    node = StrategyGuiSim()
    app = create_app(node)

    executor = SingleThreadedExecutor()
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=False, name="ros2-spin")
    spin_thread.start()

    node.get_logger().info(
        "\n"
        "  =============================================\n"
        f"  RoboCup Sim 2D UI: http://localhost:{node.ui_port}\n"
        "  =============================================",
    )

    config = uvicorn.Config(app, host="0.0.0.0", port=node.ui_port, log_level="warning")
    server = uvicorn.Server(config)
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        executor.shutdown(timeout_sec=2.0)
        spin_thread.join(timeout=2.0)
        if node._gc_udp_sock is not None:
            try:
                node._gc_udp_sock.close()
            except OSError:
                pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
