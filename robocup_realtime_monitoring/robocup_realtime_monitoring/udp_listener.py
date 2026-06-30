from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Any

TEAM_MESSAGE_PORT_BASE = 10000

# MessageV2 (little-endian, packed). Total size 350 bytes.
# Layout must be kept in sync with the C++ MessageV2 struct in the robot sender.
# Runtime always uses self._struct.size for length checks (definitive).
_MSG_FMT = (
    "<"
    "i"      # player_id
    "fff"    # position (x, y, theta)
    "fff"    # pose_mc
    "fff"    # pose_vslam
    "fff"    # pose_robot_odom
    "i"      # direction_check
    "ff"     # eval_scores[2]
    "fff"    # walk_command
    "ff"     # kick_target
    "ff"     # ball_position (x, y)
    "ff"     # ball_velocity
    "ffff"   # ball_covariance (2x2)
    "ffff"   # pose_covariance (2x2)
    "ff"     # self_ball_position
    "ifff"   # other_robot (player_id + position) — 1st teammate obs
    "fff"    # other_robot_cov (σ²x, σ²y, σ²yaw)
    "ifff"   # other_robot_2 — 2nd teammate obs
    "fff"    # other_robot_2_cov
    "ifff"   # other_robot1 (opponent 1)
    "ifff"   # other_robot2 (opponent 2)
    "ifff"   # other_robot3 (opponent 3)
    "i"      # pass_sequence
    "???"    # communication_check, ball_detected, penalty
    "fff"    # tf_odom_in_map
    "fff"    # result_cov
    "fff"    # mc_cov
    "fff"    # vslam_cov
    "B"      # action (uint8 enum) — appended at the end of the struct
    # === Fused world model (2026-06-15, 300B→337B append) — byte-for-byte match with sender MessageV2 ===
    "B"      # fused_ball_num_sources (idx 78)
    "ff"     # fused_ball_position x,y (idx 79,80)
    "B"      # fused_enemy_count (idx 81)
    "ff"     # fused_enemy1_pos x,y (idx 82,83)
    "B"      # fused_enemy1_num_sources (idx 84)
    "ff"     # fused_enemy2_pos x,y (idx 85,86)
    "B"      # fused_enemy2_num_sources (idx 87)
    "ff"     # fused_enemy3_pos x,y (idx 88,89)
    "B"      # fused_enemy3_num_sources (idx 90)
    "B"      # role (idx 91) — 1=player, 2=goal_keeper, 0=unknown
    "B"      # secs_till_unpenalised (idx 92) — 0=not penalised
    # === Correction status debug (2026-06-18, 339B→350B) — localization CorrectionStatus 11 bytes ===
    # strategy_gui does not display these fields, but calcsize is padded to 350 to prevent packet drops.
    # (localization CorrectionStatus 11 bytes — not parsed by this tool, size only)
    "B"      # cs_active_source (idx 93)
    "B"      # cs_veto_code (idx 94)
    "B"      # cs_mcl_gate_flags (idx 95)
    "B"      # cs_vslam_gate_flags (idx 96)
    "B"      # cs_coop_gate_flags (idx 97)
    "B"      # cs_hold_active (idx 98)
    "B"      # cs_cooldown_active (idx 99)
    "B"      # cs_coop_d2 (idx 100)
    "B"      # cs_vslam_inliers (idx 101)
    "B"      # cs_coop_abstain_reason (idx 102)
    "B"      # cs_coop_counts (idx 103)
    "B"      # cs_mcl_kp_score (idx 104) — MCL keypoint score ×255
)

_ACTION_NAMES = (
    "none", "move_to", "turn_to", "kick", "pass", "dribble",
    "stop_move", "spin_search", "recheck_wait", "save_ball_to_destination",
    "mark_buildup_passed", "reset_buildup_pass",
)

# Field indices in the parsed tuple
_IDX_PLAYER_ID = 0
_IDX_POS_X = 1
_IDX_POS_Y = 2
_IDX_POS_TH = 3
_IDX_EVAL_MC = 14       # eval_scores[0] = monte carlo score
_IDX_EVAL_VSLAM = 15    # eval_scores[1] = vslam score
_IDX_WALK_X = 16
_IDX_WALK_Y = 17
_IDX_WALK_TH = 18
_IDX_BALL_X = 21
_IDX_BALL_Y = 22
_IDX_OR1_X = 50         # other_robot1 position x (vision-detected opponent robot)
_IDX_OR1_Y = 51         # other_robot1 position y
_IDX_OR2_X = 54         # other_robot2 position x
_IDX_OR2_Y = 55         # other_robot2 position y
_IDX_OR3_X = 58         # other_robot3 position x
_IDX_OR3_Y = 59         # other_robot3 position y
_IDX_COMM_CHECK = 62    # communication_check
_IDX_BALL_DETECTED = 63
_IDX_PENALTY = 64       # penalty flag
_IDX_COV_X = 68         # result_cov 1σ (x, y, θ)
_IDX_COV_Y = 69
_IDX_COV_TH = 70
_IDX_ACTION = 77        # action enum (uint8): 0=none,1=move_to,2=turn_to,3=kick,4=pass,5=dribble
# === Fused world model indices (2026-06-15) — num_sources==0 = empty slot / invalid ===
_IDX_FUSED_BALL_NS = 78      # fused ball confidence (number of contributing observations). 0 = no fusion
_IDX_FUSED_BALL_X = 79
_IDX_FUSED_BALL_Y = 80
_IDX_FUSED_ENEMY_COUNT = 81  # number of valid fused enemies (0..3)
_IDX_FE1_X = 82
_IDX_FE1_Y = 83
_IDX_FE1_NS = 84
_IDX_FE2_X = 85
_IDX_FE2_Y = 86
_IDX_FE2_NS = 87
_IDX_FE3_X = 88
_IDX_FE3_Y = 89
_IDX_FE3_NS = 90
_IDX_ROLE = 91          # 1=player, 2=goal_keeper, 0=unknown
_IDX_SECS_UNPEN = 92    # seconds remaining until unpenalised (0=not penalised)


class UdpTeamListener:
    """Binds to 0.0.0.0:port to receive MessageV2 broadcasts and inject them into LiveState."""

    def __init__(
        self,
        live_state: Any,
        port: int,
        bind_addr: str = "0.0.0.0",
        logger: Any = None,
    ) -> None:
        self._ls = live_state
        self._port = int(port)
        self._bind = bind_addr
        self._log = logger
        self._struct = struct.Struct(_MSG_FMT)
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        # No-receive diagnostics: warn once if 0 packets received within N seconds (makes subnet/port/sender issues visible).
        self._rx_count = 0
        self._started_at = 0.0
        self._silent_warn_sec = 5.0
        self._warned_silent = False
        # Packet size mismatch
        self._warned_size = False

    # Logging helpers (fall back to print when no logger is provided).
    def _info(self, m: str) -> None:
        if self._log is not None:
            self._log.info(m)
        else:
            print(f"[robocup_strategy_gui][udp] {m}")

    def _warn(self, m: str) -> None:
        if self._log is not None:
            self._log.warn(m)
        else:
            print(f"[robocup_strategy_gui][udp] WARN: {m}")

    def start(self) -> bool:
        """Bind socket and start receiver thread. Does not throw on failure (GUI remains functional)."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # SO_REUSEPORT: share the same port with other listeners (e.g. receiver); all receive broadcasts.
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass  # not supported on this platform — proceed with REUSEADDR only
            s.bind((self._bind, self._port))
            s.settimeout(0.5)  # for periodic stop flag check
        except OSError as e:
            self._warn(
                f"UDP bind failed {self._bind}:{self._port} — {e!r}. Realtime position disabled.",
            )
            return False
        self._sock = s
        self._started_at = time.monotonic()
        self._thread = threading.Thread(
            target=self._loop, name="robocup-udp-team", daemon=True,
        )
        self._thread.start()
        self._info(
            f"UDP team communication receive started: {self._bind}:{self._port} "
            f"(MessageV2 {self._struct.size}B)",
        )
        return True

    def _loop(self) -> None:
        size = self._struct.size
        unpack_from = self._struct.unpack_from
        while not self._stop.is_set():
            try:
                data, _addr = self._sock.recvfrom(2048)
            except socket.timeout:
                self._maybe_warn_silent()
                continue
            except OSError:
                break  # socket closed → exit
            if len(data) != size:
                # Size mismatch → parsing would shift fields, producing garbage (e.g. ghost opponents at origin) → drop.
                # Only warn for packets where player_id (offset 0) is in our range (1..7):
                # prevents false positives from external traffic (e.g. game_controller) on the same REUSEPORT port.
                if len(data) >= 4:
                    pid = struct.unpack_from("<i", data, 0)[0]
                    if 1 <= pid <= 7:
                        self._maybe_warn_size(len(data))
                continue
            self._rx_count += 1
            try:
                u = unpack_from(data, 0)
            except struct.error:
                continue
            player_id = u[_IDX_PLAYER_ID]
            if player_id <= 0 or player_id >= 8:
                continue  # valid player_id range: 1..7
            try:
                self._ls.update_from_udp(player_id, {
                    "x": u[_IDX_POS_X],
                    "y": u[_IDX_POS_Y],
                    "theta": u[_IDX_POS_TH],
                    "ball_x": u[_IDX_BALL_X],
                    "ball_y": u[_IDX_BALL_Y],
                    "ball_detected": bool(u[_IDX_BALL_DETECTED]),
                    "wcmd_x": u[_IDX_WALK_X],
                    "wcmd_y": u[_IDX_WALK_Y],
                    "wcmd_theta": u[_IDX_WALK_TH],
                    # ── Robot status panel fields (already present in MessageV2) ──
                    "eval_mc": u[_IDX_EVAL_MC],
                    "eval_vslam": u[_IDX_EVAL_VSLAM],
                    "cov_x": u[_IDX_COV_X],
                    "cov_y": u[_IDX_COV_Y],
                    "cov_theta": u[_IDX_COV_TH],
                    "comm_check": bool(u[_IDX_COMM_CHECK]),
                    "penalty": bool(u[_IDX_PENALTY]),
                    # Up to 3 vision-detected opponent robots (if not detected, (0,0) → filtered out in live_state)
                    "or1_x": u[_IDX_OR1_X], "or1_y": u[_IDX_OR1_Y],
                    "or2_x": u[_IDX_OR2_X], "or2_y": u[_IDX_OR2_Y],
                    "or3_x": u[_IDX_OR3_X], "or3_y": u[_IDX_OR3_Y],
                    # Current action (BT node-based): enum → string
                    "action": _ACTION_NAMES[u[_IDX_ACTION]]
                    if u[_IDX_ACTION] < len(_ACTION_NAMES) else "none",
                    # ── Fused world model (per-robot) ──
                    # Each robot transmits its own local fused view. Fields that were previously
                    # unpacked and discarded solely for calcsize alignment are now restored —
                    # live_state stores and exposes them per robot.
                    # num_sources==0 = no fusion (empty slot). Colors (green/yellow) are derived by the GUI.
                    "fused_ball_ns": int(u[_IDX_FUSED_BALL_NS]),
                    "fused_ball_x": u[_IDX_FUSED_BALL_X],
                    "fused_ball_y": u[_IDX_FUSED_BALL_Y],
                    "fused_enemy_count": int(u[_IDX_FUSED_ENEMY_COUNT]),
                    "fe1_x": u[_IDX_FE1_X], "fe1_y": u[_IDX_FE1_Y], "fe1_ns": int(u[_IDX_FE1_NS]),
                    "fe2_x": u[_IDX_FE2_X], "fe2_y": u[_IDX_FE2_Y], "fe2_ns": int(u[_IDX_FE2_NS]),
                    "fe3_x": u[_IDX_FE3_X], "fe3_y": u[_IDX_FE3_Y], "fe3_ns": int(u[_IDX_FE3_NS]),
                })
            except Exception:  # noqa: BLE001 — receiver loop stability takes priority
                continue

    def _maybe_warn_silent(self) -> None:
        """Warn once if 0 packets received within _silent_warn_sec seconds after start.

        Instead of a silent empty overlay, lets the operator immediately see the cause:
        sender not running / team_number(port) mismatch / broadcast subnet (inet_address) unreachable.
        """
        if self._warned_silent or self._rx_count > 0 or self._warned_size:
            return
        if time.monotonic() - self._started_at < self._silent_warn_sec:
            return
        self._warned_silent = True
        self._warn(
            f"0 UDP packets received in {self._silent_warn_sec:.0f}s "
            f"({self._bind}:{self._port}). Check: (1) robocup_udp_sender is running, "
            f"(2) team_number→port match (port=10000+team_number), "
            f"(3) sender broadcast address reaches this host (subnet/firewall).",
        )

    def _maybe_warn_size(self, got: int) -> None:
        """Warn once on packet size mismatch. Indicates _MSG_FMT is out of sync with C++ MessageV2."""
        if self._warned_size:
            return
        self._warned_size = True
        self._warn(
            f"Packet size mismatch: {self._struct.size}B expected -> {got}B received. "
            f"Packet dropped. Align _MSG_FMT / _IDX_* with the robot sender's MessageV2 struct.",
        )

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()  # unblock recvfrom
            except OSError:
                pass
