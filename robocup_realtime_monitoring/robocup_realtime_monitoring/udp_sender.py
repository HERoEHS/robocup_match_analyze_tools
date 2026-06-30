"""UDP MessageV2 sender — broadcast ROS2 robot state as team UDP packets.

One instance per robot (parameterised by robot_id). Subscribes to
  {prefix}/udp/data  (RoboCupRobotData)
  {prefix}/cooperative_perception/enemies  (ObservedRobotArray)
and broadcasts a MessageV2 binary packet so UdpTeamListener (realtime
monitoring web GUI) can receive it without any external sender dependency.

Typical use:
  robot_id > 0  →  prefix = /robocup_{robot_id}   (per-robot namespace)
  robot_id <= 0 →  prefix = /robocup              (single-robot / debug)
"""
from __future__ import annotations

import socket
import struct
import threading

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy

from robocup_msgs.msg import ObservedRobotArray, RoboCupRobotData

from robocup_realtime_monitoring.udp_listener import (
    _ACTION_NAMES,
    _MSG_FMT,
    TEAM_MESSAGE_PORT_BASE,
)

_ACTION_INDEX: dict[str, int] = {name: i for i, name in enumerate(_ACTION_NAMES)}
_STRUCT = struct.Struct(_MSG_FMT)


class UdpSender(Node):
    def __init__(self) -> None:
        super().__init__("robocup_udp_sender")

        self.declare_parameter("robot_id", 1)
        self.declare_parameter("team_number", 25)
        self.declare_parameter("udp_port", 0)
        self.declare_parameter("udp_broadcast_addr", "255.255.255.255")
        self.declare_parameter("role", 1)        # 1=player, 2=goalkeeper, 0=unknown
        self.declare_parameter("send_rate_hz", 10.0)

        robot_id = int(self.get_parameter("robot_id").value)
        team_number = int(self.get_parameter("team_number").value)
        udp_port = int(self.get_parameter("udp_port").value)
        if udp_port <= 0:
            udp_port = TEAM_MESSAGE_PORT_BASE + team_number
        self._broadcast_addr: str = (
            self.get_parameter("udp_broadcast_addr").value or "255.255.255.255"
        )
        self._port = udp_port
        self._role = max(0, min(255, int(self.get_parameter("role").value)))
        send_rate = float(self.get_parameter("send_rate_hz").value)
        if send_rate <= 0:
            send_rate = 10.0
        self._robot_id = robot_id

        prefix = f"/robocup_{robot_id}" if robot_id > 0 else "/robocup"

        self._lock = threading.Lock()
        self._latest_data: RoboCupRobotData | None = None
        self._latest_enemies: ObservedRobotArray | None = None

        best_effort = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        self.create_subscription(
            RoboCupRobotData,
            f"{prefix}/udp/data",
            self._on_data,
            best_effort,
        )
        self.create_subscription(
            ObservedRobotArray,
            f"{prefix}/cooperative_perception/enemies",
            self._on_enemies,
            best_effort,
        )

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.create_timer(1.0 / send_rate, self._tick)

        self.get_logger().info(
            f"UDP sender: robot_id={robot_id} topic={prefix}/udp/data "
            f"→ {self._broadcast_addr}:{udp_port} role={self._role} "
            f"MessageV2 {_STRUCT.size}B"
        )

    def _on_data(self, msg: RoboCupRobotData) -> None:
        with self._lock:
            self._latest_data = msg

    def _on_enemies(self, msg: ObservedRobotArray) -> None:
        with self._lock:
            self._latest_enemies = msg

    def _tick(self) -> None:
        with self._lock:
            msg = self._latest_data
            enemies = self._latest_enemies
        if msg is None:
            return
        payload = self._pack(msg, enemies)
        try:
            self._sock.sendto(payload, (self._broadcast_addr, self._port))
        except OSError as e:
            self.get_logger().warn(
                f"UDP send failed: {e!r}", throttle_duration_sec=5.0,
            )

    def _pack(
        self,
        msg: RoboCupRobotData,
        enemies: ObservedRobotArray | None,
    ) -> bytes:
        # ── position ──────────────────────────────────────────────────
        rid = int(msg.current_pose.player_id) or self._robot_id
        px = float(msg.current_pose.position.x)
        py = float(msg.current_pose.position.y)
        pth = float(msg.current_pose.position.theta)
        cov = msg.current_pose.covariance        # 36-element row-major
        cov_x = float(cov[0]) if len(cov) > 0 else 0.04
        cov_y = float(cov[7]) if len(cov) > 7 else 0.04
        cov_th = float(cov[35]) if len(cov) > 35 else 0.05

        # ── motion ────────────────────────────────────────────────────
        wcmd_x = float(msg.walk_command.x)
        wcmd_y = float(msg.walk_command.y)
        wcmd_th = float(msg.walk_command.theta)
        kick_x = float(msg.kick_target.x)
        kick_y = float(msg.kick_target.y)

        # ── ball ──────────────────────────────────────────────────────
        ball_x = float(msg.ball.position.x)
        ball_y = float(msg.ball.position.y)
        ball_vx = float(msg.ball.velocity.x)
        ball_vy = float(msg.ball.velocity.y)
        ball_det = bool(msg.ball.detected.data)

        # ── misc ──────────────────────────────────────────────────────
        pass_seq = int(msg.pass_sequence.data)
        penalty = bool(msg.penalty.data)
        action_idx = _ACTION_INDEX.get(str(msg.state.data or "none"), 0)

        # ── teammate observations (others[]) ──────────────────────────
        or1_id, or1_x, or1_y, or1_th = 0, 0.0, 0.0, 0.0
        or1_cx, or1_cy, or1_cth = 0.04, 0.04, 0.05
        or2_id, or2_x, or2_y, or2_th = 0, 0.0, 0.0, 0.0
        or2_cx, or2_cy, or2_cth = 0.04, 0.04, 0.05
        for i, other in enumerate(msg.others[:2]):
            oc = other.covariance
            ox = float(other.position.x)
            oy = float(other.position.y)
            oth = float(other.position.theta)
            ocx = float(oc[0]) if len(oc) > 0 else 0.04
            ocy = float(oc[7]) if len(oc) > 7 else 0.04
            octh = float(oc[35]) if len(oc) > 35 else 0.05
            if i == 0:
                or1_id, or1_x, or1_y, or1_th = int(other.player_id), ox, oy, oth
                or1_cx, or1_cy, or1_cth = ocx, ocy, octh
            else:
                or2_id, or2_x, or2_y, or2_th = int(other.player_id), ox, oy, oth
                or2_cx, or2_cy, or2_cth = ocx, ocy, octh

        # ── fused enemies → raw enemy slots + fused world-model slots ─
        en1_x, en1_y = 0.0, 0.0
        en2_x, en2_y = 0.0, 0.0
        en3_x, en3_y = 0.0, 0.0
        fe1_x, fe1_y, fe1_ns = 0.0, 0.0, 0
        fe2_x, fe2_y, fe2_ns = 0.0, 0.0, 0
        fe3_x, fe3_y, fe3_ns = 0.0, 0.0, 0
        fused_count = 0
        if enemies is not None:
            obs = enemies.observations
            ns_list = list(enemies.observation_num_sources)
            for i, ob in enumerate(obs[:3]):
                ox = float(ob.position.x)
                oy = float(ob.position.y)
                ns = int(ns_list[i]) if i < len(ns_list) else 1
                if i == 0:
                    en1_x, en1_y = ox, oy
                    fe1_x, fe1_y, fe1_ns = ox, oy, ns
                elif i == 1:
                    en2_x, en2_y = ox, oy
                    fe2_x, fe2_y, fe2_ns = ox, oy, ns
                else:
                    en3_x, en3_y = ox, oy
                    fe3_x, fe3_y, fe3_ns = ox, oy, ns
            fused_count = min(len(obs), 3)

        return _STRUCT.pack(
            # ── position (idx 0-12) ──────────────────────────────────
            rid,
            px, py, pth,              # position
            px, py, pth,              # pose_mc (same; no separate MC estimate)
            0.0, 0.0, 0.0,            # pose_vslam
            0.0, 0.0, 0.0,            # pose_robot_odom
            # ── direction/eval (idx 13-15) ───────────────────────────
            0,                         # direction_check
            0.0, 0.0,                 # eval_scores[2]
            # ── motion (idx 16-20) ───────────────────────────────────
            wcmd_x, wcmd_y, wcmd_th,
            kick_x, kick_y,
            # ── ball (idx 21-28) ─────────────────────────────────────
            ball_x, ball_y,
            ball_vx, ball_vy,
            0.03, 0.0, 0.0, 0.03,    # ball_covariance 2×2
            # ── pose covariance / self ball (idx 29-34) ──────────────
            cov_x, 0.0, 0.0, cov_y,  # pose_covariance 2×2 diagonal
            ball_x, ball_y,           # self_ball_position
            # ── teammate observations (idx 35-48) ────────────────────
            or1_id, or1_x, or1_y, or1_th,
            or1_cx, or1_cy, or1_cth,
            or2_id, or2_x, or2_y, or2_th,
            or2_cx, or2_cy, or2_cth,
            # ── vision enemy slots (idx 49-60) ───────────────────────
            0, en1_x, en1_y, 0.0,
            0, en2_x, en2_y, 0.0,
            0, en3_x, en3_y, 0.0,
            # ── flags (idx 61-64) ────────────────────────────────────
            pass_seq,
            True, ball_det, penalty,  # comm_check=True (we're sending)
            # ── covariance detail (idx 65-76) ────────────────────────
            0.0, 0.0, 0.0,            # tf_odom_in_map
            cov_x, cov_y, cov_th,    # result_cov
            0.0, 0.0, 0.0,            # mc_cov
            0.0, 0.0, 0.0,            # vslam_cov
            # ── action (idx 77) ──────────────────────────────────────
            action_idx,
            # ── fused world-model (idx 78-92) ────────────────────────
            0,                         # fused_ball_ns (no fused ball topic)
            0.0, 0.0,                 # fused_ball_position
            fused_count,
            fe1_x, fe1_y, fe1_ns,
            fe2_x, fe2_y, fe2_ns,
            fe3_x, fe3_y, fe3_ns,
            self._role,               # role (idx 91)
            0,                         # secs_till_unpenalised (idx 92)
            # ── CorrectionStatus 12 B (idx 93-104, zero-filled) ──────
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = UdpSender()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
