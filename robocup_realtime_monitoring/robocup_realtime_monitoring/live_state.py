from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


# When multiple robots see the same opponent simultaneously, duplicate markers appear.
# Detections within this distance (m) are treated as the same opponent and merged.
_OPP_MERGE_M = 0.5


def _merge_opponents(
    raw: list[tuple[float, float, int]],
) -> list[dict[str, Any]]:
    """Merge vision-detected opponent coordinates into nearby clusters.

    raw: [(x, y, source_pid), ...]. Returns: [{x, y, seen_by}], where seen_by = number
    of robots that saw this opponent simultaneously (higher overlap = higher confidence).
    Greedy — absorbed into the first cluster center.
    """
    clusters: list[dict[str, Any]] = []
    for ox, oy, _pid in raw:
        hit = None
        for c in clusters:
            if (c["x"] - ox) ** 2 + (c["y"] - oy) ** 2 <= _OPP_MERGE_M ** 2:
                hit = c
                break
        if hit is None:
            clusters.append({"x": ox, "y": oy, "seen_by": 1})
        else:
            hit["seen_by"] += 1
    for c in clusters:
        c["x"] = round(c["x"], 4)
        c["y"] = round(c["y"], 4)
    return clusters


# Each robot estimates the ball position based on its own localization, so coordinates
# differ slightly for the same ball. Estimates within this distance (m) are merged as one ball.
_BALL_MERGE_M = 0.3

# Self-observation matching distance (m) for fused enemies: if a raw enemy seen by this
# robot and a fused enemy position are within this distance, it is considered "directly seen"
# (green); otherwise "seen via teammate" (yellow).
# Threshold for "directly seen" (green) vs "seen via teammate" (yellow) = 1.0m.
_SELF_OBS_MATCH_M = 1.0


def _merge_balls(
    raw: list[tuple[float, float, int, float]],
) -> list[dict[str, Any]]:
    """Merge per-robot ball estimates into nearby clusters.

    raw: [(x, y, source_pid, age), ...]. Returns: [{x, y, seen_by, age, ...}].
    seen_by = number of robots that saw this ball simultaneously (higher overlap = higher
    confidence). If seen_by==1, includes source/source_name (labeled 'robotN' on the front end).
    age = minimum (most recent) age within the cluster (used for fade determination).
    Greedy — absorbed into the position of the first (lowest pid) estimate.
    """
    clusters: list[dict[str, Any]] = []
    for bx, by, pid, age in raw:
        hit = None
        for c in clusters:
            if (c["x"] - bx) ** 2 + (c["y"] - by) ** 2 <= _BALL_MERGE_M ** 2:
                hit = c
                break
        if hit is None:
            clusters.append(
                {"x": bx, "y": by, "seen_by": 1, "age": age, "_pid": pid},
            )
        else:
            hit["seen_by"] += 1
            if age < hit["age"]:
                hit["age"] = age
    out: list[dict[str, Any]] = []
    for c in clusters:
        d: dict[str, Any] = {
            "x": round(c["x"], 4),
            "y": round(c["y"], 4),
            "seen_by": c["seen_by"],
            "age": round(c["age"], 3),
        }
        if c["seen_by"] == 1:
            d["source"] = c["_pid"]
            d["source_name"] = f"robot{c['_pid']}"
        out.append(d)
    return out


@dataclass
class _RobotEntry:
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0
    t_pose: float = -1.0       # monotonic seconds. -1 = not yet received
    ball_x: float = 0.0
    ball_y: float = 0.0
    ball_detected: bool = False
    t_ball: float = -1.0       # timestamp when a ball_detected=True packet was received
    wcmd_x: float = 0.0
    wcmd_y: float = 0.0
    wcmd_theta: float = 0.0
    wcmd_valid: bool = False   # whether a valid (non-zero) command has been received at least once
    # ── Robot status panel fields (already present in MessageV2) ──
    eval_mc: float = 0.0       # localization score (monte carlo)
    eval_vslam: float = 0.0    # localization score (vslam)
    cov_x: float = 0.0         # result_cov 1σ (standard deviation)
    cov_y: float = 0.0
    cov_theta: float = 0.0
    comm_check: bool = False   # communication_check
    penalty: bool = False      # penalty status
    action: str = "none"       # action (none/move_to/turn_to/kick/pass/dribble)
    # Vision-detected opponent robot coordinates [(x, y), ...] — opponents seen by this robot's camera.
    opponents: list = field(default_factory=list)
    # ── Fused world model (per-robot; each robot transmits its own fused view) ──
    # num_sources==0 = invalid → retain last good value (hold-last-good); freshness expires by timestamp.
    fused_ball_x: float = 0.0
    fused_ball_y: float = 0.0
    fused_ball_ns: int = 0          # number of observations contributing to fused ball (0=no fusion)
    t_fused_ball: float = -1.0
    fused_enemies: list = field(default_factory=list)  # [(x, y, num_sources), ...] up to 3 (anonymous)
    t_fused_enemies: float = -1.0


class LiveState:
    """Stores the latest global pose and ball estimate per player_id (=robotN).

    A slot is dynamically created per player_id on each UDP packet (no pre-registration needed).
    Only data within stale_sec is exposed in the snapshot.
    skip_zero_pose: packets with position exactly (0,0,0) are considered uninitialized
      localization and excluded from display (prevents ghost robots at field center).
      The sender init default is (0,0,0).
    """

    def __init__(
        self,
        stale_sec: float = 2.0,
        skip_zero_pose: bool = True,
        ball_requires_detected: bool = False,
    ) -> None:
        self._lock = threading.Lock()
        self._robots: dict[int, _RobotEntry] = {}
        self._stale = float(stale_sec)
        self._skip_zero = bool(skip_zero_pose)
        # ball_requires_detected:
        #   False (default): ignore the ball_detected flag; display if ball_position is valid.
        #     → In simulation, ball_detected is always false because there is no
        #       vision_process publishing detected_ball(Bool), but ball_position from
        #       detected_objects is populated every tick, so this mode is required to see the ball.
        #   True: only accept packets with ball_detected=True as valid (for real vision pipelines).
        self._ball_requires_detected = bool(ball_requires_detected)

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    def update_from_udp(self, player_id: int, f: dict[str, Any]) -> None:
        now = self._now()
        wcmd_x = float(f.get("wcmd_x", 0.0))
        wcmd_y = float(f.get("wcmd_y", 0.0))
        wcmd_theta = float(f.get("wcmd_theta", 0.0))
        ball_x = float(f["ball_x"])
        ball_y = float(f["ball_y"])
        with self._lock:
            e = self._robots.get(player_id)
            if e is None:
                e = self._robots[player_id] = _RobotEntry()
            e.x = float(f["x"])
            e.y = float(f["y"])
            e.theta = float(f["theta"])
            e.t_pose = now
            e.ball_detected = bool(f["ball_detected"])
            e.wcmd_x = wcmd_x
            e.wcmd_y = wcmd_y
            e.wcmd_theta = wcmd_theta
            e.wcmd_valid = not (wcmd_x == 0.0 and wcmd_y == 0.0 and wcmd_theta == 0.0)
            # ── Status panel fields ──
            e.eval_mc = float(f.get("eval_mc", 0.0))
            e.eval_vslam = float(f.get("eval_vslam", 0.0))
            e.cov_x = float(f.get("cov_x", 0.0))
            e.cov_y = float(f.get("cov_y", 0.0))
            e.cov_theta = float(f.get("cov_theta", 0.0))
            e.comm_check = bool(f.get("comm_check", False))
            e.penalty = bool(f.get("penalty", False))
            e.action = str(f.get("action", "none"))
            # Vision-detected opponent robots: (0,0) means "not detected", so exclude.
            opp: list[tuple[float, float]] = []
            for kx, ky in (("or1_x", "or1_y"), ("or2_x", "or2_y"), ("or3_x", "or3_y")):
                ox, oy = f.get(kx), f.get(ky)
                if ox is None or oy is None:
                    continue
                if ox == 0.0 and oy == 0.0:
                    continue
                opp.append((float(ox), float(oy)))
            e.opponents = opp
            # Ball position is stored regardless of the ball_detected flag.
            # (0,0) is treated as uninitialized/invalid and ignored → expires naturally.
            # In simulation, ball_position is valid even when ball_detected is always false,
            # so this is required for the ball to appear. Display policy (whether detected
            # is required) is determined in snapshot.
            if not (ball_x == 0.0 and ball_y == 0.0):
                e.ball_x = ball_x
                e.ball_y = ball_y
                e.t_ball = now
            # ── Fused world model (per-robot) ── num_sources==0 = invalid → do not update (hold-last-good).
            fb_ns = int(f.get("fused_ball_ns", 0))
            if fb_ns > 0:
                fbx = float(f.get("fused_ball_x", 0.0))
                fby = float(f.get("fused_ball_y", 0.0))
                if not (fbx == 0.0 and fby == 0.0):
                    e.fused_ball_x = fbx
                    e.fused_ball_y = fby
                    e.fused_ball_ns = fb_ns
                    e.t_fused_ball = now
            if int(f.get("fused_enemy_count", 0)) > 0:
                fes: list[tuple[float, float, int]] = []
                for kx, ky, kn in (
                    ("fe1_x", "fe1_y", "fe1_ns"),
                    ("fe2_x", "fe2_y", "fe2_ns"),
                    ("fe3_x", "fe3_y", "fe3_ns"),
                ):
                    ex, ey = f.get(kx), f.get(ky)
                    if ex is None or ey is None:
                        continue
                    if ex == 0.0 and ey == 0.0:
                        continue  # empty slot
                    fes.append((float(ex), float(ey), int(f.get(kn, 0))))
                if fes:
                    e.fused_enemies = fes
                    e.t_fused_enemies = now

    def snapshot(self) -> dict[str, Any]:
        """Snapshot for front-end polling.

        robots: only robots with a pose within stale_sec (skip_zero_pose applied), sorted by id ascending.
        ball: the freshest single estimate among robots currently detecting the ball.
        """
        now = self._now()
        with self._lock:
            robots: list[dict[str, Any]] = []
            raw_opp: list[tuple[float, float, int]] = []  # vision-detected opponents (before merging)
            raw_ball: list[tuple[float, float, int, float]] = []  # per-robot ball estimates (before merging)
            for pid, e in sorted(self._robots.items()):
                if e.t_pose < 0:
                    continue
                age = now - e.t_pose
                if age > self._stale:
                    continue
                if self._skip_zero and e.x == 0.0 and e.y == 0.0 and e.theta == 0.0:
                    continue
                robot = {
                    "id": pid,
                    "name": f"robot{pid}",
                    "x": round(e.x, 4),
                    "y": round(e.y, 4),
                    "theta": round(e.theta, 5),
                    "age": round(age, 3),
                    # ── Status panel ──
                    "penalty": e.penalty,
                    "comm": e.comm_check,
                    "ball_detected": e.ball_detected,
                    "action": e.action,
                    # Global ball coordinates estimated by this robot (only when valid and fresh, else None)
                    "ball_pos": (
                        {"x": round(e.ball_x, 4), "y": round(e.ball_y, 4)}
                        if (
                            e.t_ball >= 0
                            and (now - e.t_ball) <= self._stale
                            and not (e.ball_x == 0.0 and e.ball_y == 0.0)
                        )
                        else None
                    ),
                    "eval": {
                        "mc": round(e.eval_mc, 3),
                        "vslam": round(e.eval_vslam, 3),
                    },
                    "cov": {
                        "x": round(e.cov_x, 4),
                        "y": round(e.cov_y, 4),
                        "theta": round(e.cov_theta, 5),
                    },
                }
                if e.wcmd_valid:
                    robot["wcmd"] = {
                        "x": round(e.wcmd_x, 4),
                        "y": round(e.wcmd_y, 4),
                        "theta": round(e.wcmd_theta, 5),
                    }
                # ── Fused world model (per-robot) — overlay drawn via sidebar toggle ──
                # self_seen: whether this robot saw it directly (magenta) vs visible only through teammates (yellow).
                #   ball = ball_detected boolean / enemy = matched within 1.0m of raw-observed enemy.
                fused_ball = None
                if (
                    e.fused_ball_ns > 0
                    and e.t_fused_ball >= 0
                    and (now - e.t_fused_ball) <= self._stale
                ):
                    fused_ball = {
                        "x": round(e.fused_ball_x, 4),
                        "y": round(e.fused_ball_y, 4),
                        "num_sources": e.fused_ball_ns,
                        "self_seen": bool(e.ball_detected),
                    }
                fused_enemies: list[dict[str, Any]] = []
                if (
                    e.fused_enemies
                    and e.t_fused_enemies >= 0
                    and (now - e.t_fused_enemies) <= self._stale
                ):
                    for ex, ey, ns in e.fused_enemies:
                        self_seen = any(
                            (ox - ex) ** 2 + (oy - ey) ** 2 <= _SELF_OBS_MATCH_M ** 2
                            for ox, oy in e.opponents
                        )
                        fused_enemies.append({
                            "x": round(ex, 4),
                            "y": round(ey, 4),
                            "num_sources": int(ns),
                            "self_seen": bool(self_seen),
                        })
                robot["fused_ball"] = fused_ball
                robot["fused_enemies"] = fused_enemies
                robots.append(robot)
                for ox, oy in e.opponents:
                    raw_opp.append((ox, oy, pid))
                if e.t_ball >= 0 and not (
                    self._ball_requires_detected and not e.ball_detected
                ):
                    age_b = now - e.t_ball
                    if age_b <= self._stale:
                        raw_ball.append((e.ball_x, e.ball_y, pid, age_b))

            # Export all per-robot balls; merge into one if within 0.3m (count seen_by).
            balls = _merge_balls(raw_ball)
            # Representative ball: single entry for ball-velocity arrow — highest seen_by, then freshest on tie.
            ball: dict[str, Any] | None = None
            if balls:
                ball = sorted(balls, key=lambda b: (-b["seen_by"], b["age"]))[0]
            return {
                "enabled": True,
                "stale_sec": self._stale,
                "robots": robots,
                "ball": ball,
                "balls": balls,
                "opponents": _merge_opponents(raw_opp),
            }
