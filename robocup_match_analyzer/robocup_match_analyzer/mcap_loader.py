"""MCAP blackbox file loader."""
from __future__ import annotations

import bisect
import math
import re
from pathlib import Path
from typing import Any

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MCAP_MIN_SIZE = 64  # bytes — anything smaller cannot be a valid MCAP file


def _open_reader(path: Path) -> rosbag2_py.SequentialReader:
    reader = rosbag2_py.SequentialReader()
    # rosbag2 creates directory bag packages (<name>.mcap/) without metadata.yaml;
    # resolve to the inner .mcap file so the storage plugin can open it directly.
    if path.is_dir() and not (path / 'metadata.yaml').exists():
        inner = sorted(path.glob('*.mcap'))
        if inner:
            path = inner[0]
    if path.is_file() and path.stat().st_size < _MCAP_MIN_SIZE:
        raise ValueError(f"MCAP file too small to be valid ({path.stat().st_size} bytes): {path}")
    reader.open(
        rosbag2_py.StorageOptions(uri=str(path), storage_id='mcap'),
        rosbag2_py.ConverterOptions('', ''),
    )
    return reader


def _local_to_global(rx: float, ry: float, rth: float,
                     lx: float, ly: float) -> tuple[float, float]:
    c, s = math.cos(rth), math.sin(rth)
    return rx + c * lx - s * ly, ry + s * lx + c * ly


def _robot_id_from_topic(topic: str) -> int | None:
    m = re.match(r'^(?:robocup_|robot)(\d+)/', topic)
    return int(m.group(1)) if m else None


def _strip_robot_prefix(topic: str) -> str:
    return re.sub(r'^(?:robocup_|robot)\d+/', '', topic)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class Session:

    def __init__(self) -> None:
        self.robot_ids: list[int] = []
        self.duration: float = 0.0
        self.start_ts_ns: int = 0

        # Per-robot pose / destination / BT / lifted
        self._pose_t:   dict[int, list[float]] = {}
        self._poses:    dict[int, list[tuple[float, float, float]]] = {}
        self._dest_t:   dict[int, list[float]] = {}
        self._dests:    dict[int, list[tuple[float, float]]] = {}
        self._bt_t:     dict[int, list[float]] = {}
        self._bt:       dict[int, list[str]] = {}
        self._lifted_t: dict[int, list[float]] = {}
        self._lifted:   dict[int, list[bool]] = {}

        # Per-robot RL velocity command (robot-local frame)
        self._vel_cmd_t:  dict[int, list[float]] = {}
        self._vel_cmds:   dict[int, list[tuple[float, float]]] = {}

        # Merged ball (global) — best estimate across all robots
        self._ball_t:  list[float] = []
        self._ball_xy: list[tuple[float, float]] = []

        # Merged enemies (global) — cooperative_perception
        self._enemy_t:      list[float] = []
        self._enemy_groups: list[list[tuple[float, float]]] = []

        # Game controller
        self._gc_t:      list[float] = []
        self._gc_states: list[dict[str, Any]] = []

        # ── Per-robot individual perception ──────────────────────────────
        # Ball: each robot's own detection (local → global transformed)
        self._per_ball_t:  dict[int, list[float]] = {}
        self._per_ball_xy: dict[int, list[tuple[float, float]]] = {}

        # Non-ball detected objects per robot: (gx, gy, name)
        # name: 'ally'=ally robot, 'robot'=enemy robot
        self._per_detect_t:    dict[int, list[float]] = {}
        self._per_detect_objs: dict[int, list[list[tuple[float, float, str]]]] = {}

        # ── Per-robot UDP received team positions ─────────────────────────
        # _udp_t[receiver_id][sender_id]  = [timestamps]
        # _udp_poses[receiver_id][sender_id] = [(x, y, theta)]
        self._udp_t:     dict[int, dict[int, list[float]]] = {}
        self._udp_poses: dict[int, dict[int, list[tuple[float, float, float]]]] = {}

        # _udp_sender_receivers[sender_id] = [receiver_id, ...]
        # Used to recover the position of robots missing localization/pose MCAP data from udp/data
        self._udp_sender_receivers: dict[int, list[int]] = {}

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def robot_data_gaps(
        self, gap_threshold_s: float = 1.0,
    ) -> dict[int, list[tuple[float, float]]]:
        """Return per-robot pose data gap intervals within [0, duration].

        Each entry is (t0, t1) where no pose data exists for that robot.
        Gaps shorter than gap_threshold_s are ignored.
        """
        t_end = self.duration
        result: dict[int, list[tuple[float, float]]] = {}
        for rid in self.robot_ids:
            times = self._pose_t.get(rid, [])
            gaps: list[tuple[float, float]] = []
            if not times:
                gaps.append((0.0, round(t_end, 3)))
                result[rid] = gaps
                continue
            # First pose in [0, t_end]
            fi = bisect.bisect_left(times, 0.0)
            if fi >= len(times) or times[fi] > t_end:
                # All data outside [0, t_end]
                gaps.append((0.0, round(t_end, 3)))
                result[rid] = gaps
                continue
            first_t = times[fi]
            if first_t > gap_threshold_s:
                gaps.append((0.0, round(first_t, 3)))
            # Internal gaps
            for i in range(fi, len(times) - 1):
                a, b = times[i], times[i + 1]
                if a >= t_end:
                    break
                b = min(b, t_end)
                if b - a > gap_threshold_s:
                    gaps.append((round(a, 3), round(b, 3)))
            # Gap at end
            li = bisect.bisect_right(times, t_end) - 1
            if li >= 0 and t_end - times[li] > gap_threshold_s:
                gaps.append((round(times[li], 3), round(t_end, 3)))
            result[rid] = gaps
        return result

    def frame_at(self, t: float) -> dict[str, Any]:
        robots: list[dict[str, Any]] = []
        for rid in self.robot_ids:
            pose_times = self._pose_t.get(rid, [])
            idx = bisect.bisect_right(pose_times, t) - 1

            if idx >= 0:
                x, y, theta = self._poses[rid][idx]
                age = round(t - pose_times[idx], 3)
                pose_source = 'localization'
            else:
                best_t: float | None = None
                best_pose: tuple[float, float, float] | None = None
                for recv_id in self._udp_sender_receivers.get(rid, []):
                    times = self._udp_t.get(recv_id, {}).get(rid, [])
                    ui = bisect.bisect_right(times, t) - 1
                    if ui >= 0 and (best_t is None or times[ui] > best_t):
                        best_t = times[ui]
                        best_pose = self._udp_poses[recv_id][rid][ui]
                if best_pose is None:
                    continue
                x, y, theta = best_pose
                age = round(t - best_t, 3)  # type: ignore[arg-type]
                pose_source = 'udp'

            robot: dict[str, Any] = {
                "id": rid,
                "x": round(x, 4), "y": round(y, 4),
                "theta": round(theta, 4),
                "age": age,
                "pose_source": pose_source,
            }
            bt_times = self._bt_t.get(rid, [])
            if bt_times:
                i = bisect.bisect_right(bt_times, t) - 1
                if i >= 0:
                    robot["bt_node"] = self._bt[rid][i]
            dest_times = self._dest_t.get(rid, [])
            if dest_times:
                i = bisect.bisect_right(dest_times, t) - 1
                if i >= 0:
                    dx, dy = self._dests[rid][i]
                    robot["dest"] = {"x": round(dx, 4), "y": round(dy, 4)}
            lifted_times = self._lifted_t.get(rid, [])
            if lifted_times:
                i = bisect.bisect_right(lifted_times, t) - 1
                if i >= 0:
                    robot["lifted"] = self._lifted[rid][i]
            vel_times = self._vel_cmd_t.get(rid, [])
            if vel_times:
                vi = bisect.bisect_right(vel_times, t) - 1
                if vi >= 0 and t - vel_times[vi] < 0.5:
                    vx, vy = self._vel_cmds[rid][vi]
                    robot["vel_cmd"] = {"vx": round(vx, 4), "vy": round(vy, 4)}
            robots.append(robot)

        ball = None
        if self._ball_t:
            i = bisect.bisect_right(self._ball_t, t) - 1
            if i >= 0:
                bx, by = self._ball_xy[i]
                ball = {"x": round(bx, 4), "y": round(by, 4),
                        "age": round(t - self._ball_t[i], 3)}

        enemies: list[dict[str, Any]] = []
        if self._enemy_t:
            i = bisect.bisect_right(self._enemy_t, t) - 1
            if i >= 0:
                enemies = [{"x": round(ex, 4), "y": round(ey, 4)}
                           for ex, ey in self._enemy_groups[i]]

        game_state = None
        if self._gc_t:
            i = bisect.bisect_right(self._gc_t, t) - 1
            if i >= 0:
                game_state = self._gc_states[i]

        per_perception: dict[str, Any] = {}
        for rid in self.robot_ids:
            entry: dict[str, Any] = {"ball": None, "objects": []}
            bt = self._per_ball_t.get(rid, [])
            if bt:
                i = bisect.bisect_right(bt, t) - 1
                if i >= 0:
                    bx, by = self._per_ball_xy[rid][i]
                    entry["ball"] = {"x": round(bx, 4), "y": round(by, 4)}
            dt = self._per_detect_t.get(rid, [])
            if dt:
                i = bisect.bisect_right(dt, t) - 1
                if i >= 0:
                    entry["objects"] = [
                        {"x": round(ox, 4), "y": round(oy, 4), "name": name}
                        for ox, oy, name in self._per_detect_objs[rid][i]
                    ]
            per_perception[str(rid)] = entry

        udp_perception: dict[str, Any] = {}
        for rid in self.robot_ids:
            entries: list[dict[str, Any]] = []
            for sender_id, times in self._udp_t.get(rid, {}).items():
                i = bisect.bisect_right(times, t) - 1
                if i >= 0:
                    x, y, theta = self._udp_poses[rid][sender_id][i]
                    entries.append({
                        "id": sender_id,
                        "x": round(x, 4), "y": round(y, 4),
                        "theta": round(theta, 4),
                    })
            udp_perception[str(rid)] = entries

        return {
            "t": round(t, 3),
            "robots": robots,
            "ball": ball,
            "enemies": enemies,
            "game_state": game_state,
            "per_perception": per_perception,
            "udp_perception": udp_perception,
        }

    def trail(self, t: float, window: float = 15.0) -> dict[int, list[dict]]:
        out: dict[int, list[dict]] = {}
        t0 = max(0.0, t - window)
        for rid, times in self._pose_t.items():
            lo = bisect.bisect_left(times, t0)
            hi = bisect.bisect_right(times, t)
            pts = [{"x": round(self._poses[rid][i][0], 4),
                    "y": round(self._poses[rid][i][1], 4),
                    "age": round(t - times[i], 3)}
                   for i in range(lo, hi)
                   if not (self._poses[rid][i][0] == 0.0
                           and self._poses[rid][i][1] == 0.0)]
            if pts:
                out[rid] = pts
        return out

    def heatmap(self, player_id: int | None, t0: float, t1: float,
                bins_x: int = 28, bins_y: int = 18) -> dict[str, Any]:
        length_m, width_m = 14.0, 9.0
        grid = [[0] * bins_x for _ in range(bins_y)]
        pids = [player_id] if player_id is not None else list(self._pose_t)
        for pid in pids:
            for t_rel, (x, y, _) in zip(
                self._pose_t.get(pid, []), self._poses.get(pid, [])
            ):
                if t_rel < t0 or t_rel > t1 or (x == 0.0 and y == 0.0):
                    continue
                ix = int((x + length_m / 2) / length_m * bins_x)
                iy = int((width_m / 2 - y) / width_m * bins_y)
                if 0 <= ix < bins_x and 0 <= iy < bins_y:
                    grid[iy][ix] += 1
        max_count = max((max(row) for row in grid), default=0)
        return {"bins_x": bins_x, "bins_y": bins_y, "grid": grid, "max_count": max_count}

    def heatmap_preload(self) -> dict[str, Any]:
        """Return all timestamped position data for client-side heatmap rendering."""
        # Robot positions: {str(pid): [[t, x, y], ...]}
        robots: dict[str, list[list[float]]] = {}
        for rid in self.robot_ids:
            pts: list[list[float]] = []
            for t_rel, (x, y, _) in zip(
                self._pose_t.get(rid, []), self._poses.get(rid, [])
            ):
                if x == 0.0 and y == 0.0:
                    continue
                pts.append([round(t_rel, 3), round(x, 4), round(y, 4)])
            robots[str(rid)] = pts

        # Ball positions: deduplicated (merge detections within 0.1 s windows)
        balls: list[list[float]] = []
        last_ball_t = -1.0
        for t_rel, (x, y) in zip(self._ball_t, self._ball_xy):
            if x == 0.0 and y == 0.0:
                continue
            if t_rel - last_ball_t < 0.1:
                continue
            balls.append([round(t_rel, 3), round(x, 4), round(y, 4)])
            last_ball_t = t_rel

        # Kick events per robot: rising edge of any BT node whose name contains "kick"
        kicks: dict[str, list[list[float]]] = {}
        for rid in self.robot_ids:
            bt_times = self._bt_t.get(rid, [])
            bt_nodes = self._bt.get(rid, [])
            pose_times = self._pose_t.get(rid, [])
            robot_kicks: list[list[float]] = []
            prev_kick = False
            for t_rel, node in zip(bt_times, bt_nodes):
                is_kick = 'kick' in node.lower()
                if is_kick and not prev_kick:
                    idx = bisect.bisect_right(pose_times, t_rel) - 1
                    if idx >= 0:
                        x, y, _ = self._poses[rid][idx]
                        if not (x == 0.0 and y == 0.0):
                            robot_kicks.append([round(t_rel, 3), round(x, 4), round(y, 4)])
                prev_kick = is_kick
            if robot_kicks:
                kicks[str(rid)] = robot_kicks

        # Half split: time when first_half transitions True → False
        half_split: float | None = None
        prev_fh: bool | None = None
        for t_rel, gc in zip(self._gc_t, self._gc_states):
            fh = gc.get('first_half', True)
            if prev_fh is True and not fh:
                half_split = round(t_rel, 3)
                break
            prev_fh = fh

        return {
            "robots": robots,
            "balls": balls,
            "kicks": kicks,
            "half_split": half_split,
            "duration": round(self.duration, 3),
        }

    def space_control_samples(
        self,
        max_samples: int = 240,
        min_dt: float = 0.5,
    ) -> dict[str, Any]:
        """Return evenly sampled robot/enemy positions for client-side space control."""
        if self.duration <= 0.0:
            times = [0.0]
        else:
            target_count = max(2, int(self.duration / max(min_dt, 0.1)) + 1)
            count = max(2, min(max_samples, target_count))
            step = self.duration / (count - 1)
            times = [i * step for i in range(count)]

        samples: list[dict[str, Any]] = []
        for t_rel in times:
            robots_at_t: list[dict[str, Any]] = []
            for rid in self.robot_ids:
                pose_times = self._pose_t.get(rid, [])
                idx = bisect.bisect_right(pose_times, t_rel) - 1
                if idx >= 0:
                    x, y, _ = self._poses[rid][idx]
                    robots_at_t.append({"id": rid, "x": round(x, 4), "y": round(y, 4)})
                else:
                    best_t: float | None = None
                    best_pose: tuple[float, float, float] | None = None
                    for recv_id in self._udp_sender_receivers.get(rid, []):
                        ut = self._udp_t.get(recv_id, {}).get(rid, [])
                        ui = bisect.bisect_right(ut, t_rel) - 1
                        if ui >= 0 and (best_t is None or ut[ui] > best_t):
                            best_t = ut[ui]
                            best_pose = self._udp_poses[recv_id][rid][ui]
                    if best_pose is not None:
                        x, y, _ = best_pose
                        robots_at_t.append({"id": rid, "x": round(x, 4), "y": round(y, 4)})

            enemies_at_t: list[dict[str, Any]] = []
            if self._enemy_t:
                ei = bisect.bisect_right(self._enemy_t, t_rel) - 1
                if ei >= 0:
                    enemies_at_t = [{"x": round(ex, 4), "y": round(ey, 4)}
                                    for ex, ey in self._enemy_groups[ei]]

            samples.append({
                "t": round(t_rel, 3),
                "robots": robots_at_t,
                "enemies": enemies_at_t,
            })

        return {
            "duration": round(self.duration, 3),
            "sample_count": len(samples),
            "samples": samples,
        }

    def game_state_events(self) -> list[dict[str, Any]]:
        return [{"t": round(t_rel, 3), **gc}
                for t_rel, gc in zip(self._gc_t, self._gc_states)]

    def _clamp_range(self, t0: float, t1: float) -> tuple[float, float]:
        start, end = sorted((float(t0), float(t1)))
        start = max(0.0, start)
        end = min(self.duration, end)
        return start, end

    def _make_segment(
        self,
        *,
        seg_id: str,
        kind: str,
        t0: float,
        t1: float,
        robot_id: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        start, end = self._clamp_range(t0, t1)
        if end - start <= 1e-6:
            return None
        seg: dict[str, Any] = {
            "id": seg_id,
            "kind": kind,
            "t0": round(start, 3),
            "t1": round(end, 3),
            "duration": round(end - start, 3),
        }
        if robot_id is not None:
            seg["robot_id"] = robot_id
        if extra:
            seg.update(extra)
        return seg

    def segment_presets(
        self,
        *,
        goal_pre_sec: float = 10.0,
        goal_post_sec: float = 10.0,
        fall_pre_sec: float = 10.0,
        fall_post_sec: float = 10.0,
    ) -> list[dict[str, Any]]:
        segments: list[dict[str, Any]] = []

        # Match-state spans
        prev_state: int | None = None
        prev_state_start: float | None = None
        prev_state_gc: dict[str, Any] | None = None
        for t_rel, gc in zip(self._gc_t, self._gc_states):
            state = int(gc.get("state", -1))
            if prev_state is None:
                prev_state = state
                prev_state_start = t_rel
                prev_state_gc = gc
                continue
            if state != prev_state:
                seg = self._make_segment(
                    seg_id=f"state:{prev_state}:{prev_state_start:.3f}",
                    kind="state_span",
                    t0=prev_state_start,
                    t1=t_rel,
                    extra={
                        "state": prev_state,
                        "first_half": bool((prev_state_gc or {}).get("first_half", True)),
                    },
                )
                if seg:
                    segments.append(seg)
                prev_state = state
                prev_state_start = t_rel
                prev_state_gc = gc
        if prev_state is not None and prev_state_start is not None:
            seg = self._make_segment(
                seg_id=f"state:{prev_state}:{prev_state_start:.3f}",
                kind="state_span",
                t0=prev_state_start,
                t1=self.duration,
                extra={
                    "state": prev_state,
                    "first_half": bool((prev_state_gc or {}).get("first_half", True)),
                },
            )
            if seg:
                segments.append(seg)

        # Set-play spans
        active_set_play: int | None = None
        active_set_play_start: float | None = None
        active_set_play_gc: dict[str, Any] | None = None
        for t_rel, gc in zip(self._gc_t, self._gc_states):
            set_play = int(gc.get("set_play", 0) or 0)
            if active_set_play is None:
                if set_play != 0:
                    active_set_play = set_play
                    active_set_play_start = t_rel
                    active_set_play_gc = gc
                continue
            if set_play != active_set_play:
                if active_set_play_start is not None:
                    seg = self._make_segment(
                        seg_id=f"setplay:{active_set_play}:{active_set_play_start:.3f}",
                        kind="setplay_span",
                        t0=active_set_play_start,
                        t1=t_rel,
                        extra={
                            "set_play": active_set_play,
                            "first_half": bool((active_set_play_gc or {}).get("first_half", True)),
                        },
                    )
                    if seg:
                        segments.append(seg)
                active_set_play = set_play if set_play != 0 else None
                active_set_play_start = t_rel if set_play != 0 else None
                active_set_play_gc = gc if set_play != 0 else None
        if active_set_play is not None and active_set_play_start is not None:
            seg = self._make_segment(
                seg_id=f"setplay:{active_set_play}:{active_set_play_start:.3f}",
                kind="setplay_span",
                t0=active_set_play_start,
                t1=self.duration,
                extra={
                    "set_play": active_set_play,
                    "first_half": bool((active_set_play_gc or {}).get("first_half", True)),
                },
            )
            if seg:
                segments.append(seg)

        # Goal windows from score changes
        prev_scores: dict[int, int] = {}
        for t_rel, gc in zip(self._gc_t, self._gc_states):
            for tm in gc.get("teams", []) or []:
                team_number = int(tm.get("team_number", 0) or 0)
                score = int(tm.get("score", 0) or 0)
                if team_number <= 0:
                    continue
                prev_score = prev_scores.get(team_number)
                if prev_score is not None and score > prev_score:
                    seg = self._make_segment(
                        seg_id=f"goal:{team_number}:{score}:{t_rel:.3f}",
                        kind="goal_window",
                        t0=t_rel - goal_pre_sec,
                        t1=t_rel + goal_post_sec,
                        extra={
                            "anchor_t": round(t_rel, 3),
                            "team_number": team_number,
                            "score": score,
                            "first_half": bool(gc.get("first_half", True)),
                        },
                    )
                    if seg:
                        segments.append(seg)
                prev_scores[team_number] = score

        # Fall-context windows
        for rid in self.robot_ids:
            lifted_times = self._lifted_t.get(rid, [])
            lifted_values = self._lifted.get(rid, [])
            fall_start: float | None = None
            prev_lifted = False
            for t_rel, lifted in zip(lifted_times, lifted_values):
                is_lifted = bool(lifted)
                if is_lifted and not prev_lifted:
                    fall_start = t_rel
                elif not is_lifted and prev_lifted and fall_start is not None:
                    seg = self._make_segment(
                        seg_id=f"fall:{rid}:{fall_start:.3f}",
                        kind="fall_window",
                        t0=fall_start - fall_pre_sec,
                        t1=fall_start + fall_post_sec,
                        robot_id=rid,
                        extra={
                            "anchor_t": round(fall_start, 3),
                            "recovered": True,
                            "recovery_duration_s": round(t_rel - fall_start, 3),
                        },
                    )
                    if seg:
                        segments.append(seg)
                    fall_start = None
                prev_lifted = is_lifted
            if fall_start is not None:
                seg = self._make_segment(
                    seg_id=f"fall:{rid}:{fall_start:.3f}",
                    kind="fall_window",
                    t0=fall_start - fall_pre_sec,
                    t1=fall_start + fall_post_sec,
                    robot_id=rid,
                    extra={
                        "anchor_t": round(fall_start, 3),
                        "recovered": False,
                        "recovery_duration_s": None,
                    },
                )
                if seg:
                    segments.append(seg)

        # Compute post-setplay possession outcome (5s window after setplay ends)
        _POST_WIN_S = 5.0
        for seg in segments:
            if seg["kind"] != "setplay_span":
                continue
            post_end = min(seg["t1"] + _POST_WIN_S, self.duration)
            if post_end <= seg["t1"] + 0.5:
                continue
            post_poss = self.possession_stats(seg["t1"], post_end)
            if not post_poss.get("available"):
                continue
            our_pct = float(post_poss.get("our_pct") or 0.0)
            enemy_pct = post_poss.get("enemy_pct")
            if enemy_pct is None:
                seg["post_possession"] = "our" if our_pct >= 30.0 else "loose"
            elif our_pct >= float(enemy_pct or 0.0) + 15:
                seg["post_possession"] = "our"
            elif float(enemy_pct or 0.0) >= our_pct + 15:
                seg["post_possession"] = "enemy"
            else:
                seg["post_possession"] = "loose"

        kind_order = {
            "state_span": 0,
            "setplay_span": 1,
            "goal_window": 2,
            "fall_window": 3,
        }
        segments.sort(
            key=lambda seg: (
                float(seg["t0"]),
                kind_order.get(str(seg.get("kind")), 99),
                int(seg.get("robot_id", 0) or 0),
            ),
        )
        return segments

    def _count_kick_events_in_range(self, rid: int, t0: float, t1: float) -> int:
        count = 0
        prev_kick = False
        for t_rel, node in zip(self._bt_t.get(rid, []), self._bt.get(rid, [])):
            node_str = str(node or "").strip()
            is_kick = "kick" in node_str.lower()
            if t_rel < t0:
                prev_kick = is_kick
                continue
            if t_rel > t1:
                break
            if is_kick and not prev_kick:
                count += 1
            prev_kick = is_kick
        return count

    def _count_fall_events_in_range(self, rid: int, t0: float, t1: float) -> int:
        count = 0
        prev_lifted = False
        for t_rel, lifted in zip(self._lifted_t.get(rid, []), self._lifted.get(rid, [])):
            is_lifted = bool(lifted)
            if t_rel < t0:
                prev_lifted = is_lifted
                continue
            if t_rel > t1:
                break
            if is_lifted and not prev_lifted:
                count += 1
            prev_lifted = is_lifted
        return count

    def _robot_stats_in_range(self, rid: int, t0: float, t1: float) -> dict[str, Any]:
        pose_times = self._pose_t.get(rid, [])
        poses = self._poses.get(rid, [])
        first_idx = bisect.bisect_left(pose_times, t0)
        last_idx = bisect.bisect_right(pose_times, t1) - 1

        # Localization jumps (fall recovery, relocalization) can cause position
        # discontinuities of several metres in one step.  Any instantaneous speed
        # above this threshold is treated as an artifact and excluded from both
        # speed and distance calculations.
        _MAX_PLAUSIBLE_SPEED_MPS = 3.0

        distance_m = 0.0
        max_speed_mps = 0.0
        sample_count = 0
        if poses and first_idx <= last_idx and first_idx < len(poses) and last_idx >= 0:
            sample_count = last_idx - first_idx + 1
            seed_idx = bisect.bisect_right(pose_times, t0) - 1
            prev_idx = seed_idx if seed_idx >= 0 else first_idx
            prev_x, prev_y, _prev_theta = poses[prev_idx]
            prev_t = pose_times[prev_idx]
            start_iter = max(first_idx, prev_idx + 1)
            for idx in range(start_iter, last_idx + 1):
                cur_x, cur_y, _cur_theta = poses[idx]
                cur_t = pose_times[idx]
                dist = math.hypot(cur_x - prev_x, cur_y - prev_y)
                dt = cur_t - prev_t
                if dt > 1e-6:
                    instant_speed = dist / dt
                    if instant_speed <= _MAX_PLAUSIBLE_SPEED_MPS:
                        distance_m += dist
                        max_speed_mps = max(max_speed_mps, instant_speed)
                prev_x, prev_y = cur_x, cur_y
                prev_t = cur_t

        kick_count = self._count_kick_events_in_range(rid, t0, t1)
        fall_count = self._count_fall_events_in_range(rid, t0, t1)
        duration = max(0.0, t1 - t0)
        avg_speed_mps = distance_m / duration if duration > 1e-6 else 0.0

        dest_times = self._dest_t.get(rid, [])
        lo = bisect.bisect_left(dest_times, t0)
        hi = bisect.bisect_right(dest_times, t1)
        dest_change_count = hi - lo

        return {
            "robot_id": rid,
            "sample_count": sample_count,
            "distance_m": round(distance_m, 3),
            "avg_speed_mps": round(avg_speed_mps, 3),
            "max_speed_mps": round(max_speed_mps, 3),
            "kick_count": kick_count,
            "fall_count": fall_count,
            "dest_change_count": dest_change_count,
            "has_pose_data": sample_count > 0,
        }

    def possession_stats(
        self,
        t0: float,
        t1: float,
        dist_m: float = 0.5,
        hold_s: float = 0.1,
    ) -> dict[str, Any]:
        _SAMPLE_HZ = 10
        _CONTROL_DIST_M = max(0.05, dist_m)
        _BALL_STALE_S = 1.0
        # Minimum consecutive samples a team must hold possession before the
        # transition is counted as a real turnover (filters boundary flicker).
        _MIN_HOLD_SAMPLES = max(1, round(hold_s * _SAMPLE_HZ))
        # Minimum consecutive samples in a new zone before counting a transition.
        _MIN_ZONE_DWELL = 5  # 0.5s at 10Hz

        start, end = self._clamp_range(t0, t1)
        duration = max(0.0, end - start)
        if not self._ball_t or duration < 1e-6:
            return {"available": False}

        enemy_tracked = bool(self._enemy_t)
        step = 1.0 / _SAMPLE_HZ
        our_samples = 0
        enemy_samples = 0
        stuck_samples = 0
        loose_samples = 0
        zone_counts = [0, 0, 0]  # left(x<-1.5), mid, right(x>1.5)
        definitive_seq: list[str] = []  # only "our" / "enemy" entries

        # Zone flow tracking with hysteresis
        zone_flow: dict[str, int] = {
            "left_to_mid": 0, "mid_to_left": 0,
            "mid_to_right": 0, "right_to_mid": 0,
            "left_to_right": 0, "right_to_left": 0,
        }
        _zf_stable: str | None = None
        _zf_pending: str | None = None
        _zf_cnt: int = 0

        t = start
        while t <= end + 1e-9:
            # ball position
            bi = bisect.bisect_right(self._ball_t, t) - 1
            if bi < 0:
                t += step
                continue
            ball_age = t - self._ball_t[bi]
            if ball_age > _BALL_STALE_S:
                t += step
                continue
            bx, by = self._ball_xy[bi]

            # zone counts + flow tracking
            if bx < -1.5:
                zone_counts[0] += 1
                _zf_cur = "left"
            elif bx > 1.5:
                zone_counts[2] += 1
                _zf_cur = "right"
            else:
                zone_counts[1] += 1
                _zf_cur = "mid"

            if _zf_stable is None:
                _zf_stable = _zf_cur
            elif _zf_cur == _zf_stable:
                _zf_pending = None
                _zf_cnt = 0
            elif _zf_cur == _zf_pending:
                _zf_cnt += 1
                if _zf_cnt >= _MIN_ZONE_DWELL:
                    _zf_key = f"{_zf_stable}_to_{_zf_pending}"
                    if _zf_key in zone_flow:
                        zone_flow[_zf_key] += 1
                    _zf_stable = _zf_pending
                    _zf_pending = None
                    _zf_cnt = 0
            else:
                _zf_pending = _zf_cur
                _zf_cnt = 1

            # nearest our robot
            min_our = float('inf')
            for rid in self.robot_ids:
                pt = self._pose_t.get(rid, [])
                ps = self._poses.get(rid, [])
                if not pt:
                    continue
                pi = bisect.bisect_right(pt, t) - 1
                if pi < 0:
                    continue
                rx, ry, _ = ps[pi]
                d = math.hypot(rx - bx, ry - by)
                if d < min_our:
                    min_our = d

            # nearest enemy
            min_enemy = float('inf')
            if enemy_tracked and self._enemy_t:
                ei = bisect.bisect_right(self._enemy_t, t) - 1
                if ei >= 0:
                    for ex, ey in self._enemy_groups[ei]:
                        d = math.hypot(ex - bx, ey - by)
                        if d < min_enemy:
                            min_enemy = d

            our_near   = min_our   < _CONTROL_DIST_M
            enemy_near = min_enemy < _CONTROL_DIST_M
            if our_near and enemy_near:
                state = "stuck"
            elif our_near:
                state = "our"
            elif enemy_near:
                state = "enemy"
            else:
                state = "loose"

            if state == "our":
                our_samples += 1
                definitive_seq.append("our")
            elif state == "enemy":
                enemy_samples += 1
                definitive_seq.append("enemy")
            elif state == "stuck":
                stuck_samples += 1
                # stuck is transparent for turnover counting (like loose)
            else:
                loose_samples += 1

            t += step

        # Run-length encode definitive possession, then filter short runs
        # (boundary flicker) before counting turnovers.
        runs: list[tuple[str, int]] = []
        for s in definitive_seq:
            if runs and runs[-1][0] == s:
                runs[-1] = (s, runs[-1][1] + 1)
            else:
                runs.append((s, 1))
        stable_runs = [r for r in runs if r[1] >= _MIN_HOLD_SAMPLES]
        turnovers_lost = 0
        turnovers_gained = 0
        for i in range(1, len(stable_runs)):
            prev_team, _ = stable_runs[i - 1]
            cur_team, _ = stable_runs[i]
            if prev_team == "our" and cur_team == "enemy":
                turnovers_lost += 1
            elif prev_team == "enemy" and cur_team == "our":
                turnovers_gained += 1

        total_valid = our_samples + enemy_samples + stuck_samples + loose_samples
        if enemy_tracked:
            bar_total = our_samples + stuck_samples + enemy_samples
        else:
            # Solo mode: bar shows time near ball vs loose
            bar_total = our_samples + loose_samples
        our_pct   = round(our_samples   / bar_total * 100, 1) if bar_total > 0 else None
        stuck_pct = round(stuck_samples / bar_total * 100, 1) if bar_total > 0 else None
        enemy_pct = round(enemy_samples / bar_total * 100, 1) if bar_total > 0 else None
        loose_pct = round(loose_samples / total_valid * 100, 1) if total_valid > 0 else None

        zone_total = sum(zone_counts)
        ball_zone = {
            "left_pct":  round(zone_counts[0] / zone_total * 100, 1) if zone_total > 0 else 0.0,
            "mid_pct":   round(zone_counts[1] / zone_total * 100, 1) if zone_total > 0 else 0.0,
            "right_pct": round(zone_counts[2] / zone_total * 100, 1) if zone_total > 0 else 0.0,
        }

        return {
            "available": True,
            "enemy_tracked": enemy_tracked,
            "our_pct": our_pct,
            "stuck_pct": stuck_pct if enemy_tracked else None,
            "enemy_pct": enemy_pct if enemy_tracked else None,
            "loose_pct": loose_pct,
            "our_seconds": round(our_samples   / _SAMPLE_HZ, 1),
            "stuck_seconds": round(stuck_samples / _SAMPLE_HZ, 1) if enemy_tracked else None,
            "enemy_seconds": round(enemy_samples / _SAMPLE_HZ, 1) if enemy_tracked else None,
            "turnovers_lost": turnovers_lost,
            "turnovers_gained": turnovers_gained,
            "ball_zone": ball_zone,
            "ball_zone_flow": zone_flow,
        }

    def _robots_at_t(self, t: float) -> list[tuple[float, float]]:
        """Return (x, y) for each robot at time t using pose or UDP fallback."""
        pts: list[tuple[float, float]] = []
        for rid in self.robot_ids:
            pose_times = self._pose_t.get(rid, [])
            idx = bisect.bisect_right(pose_times, t) - 1
            if idx >= 0:
                x, y, _ = self._poses[rid][idx]
                pts.append((x, y))
            else:
                best_t: float | None = None
                best_pose: tuple[float, float, float] | None = None
                for recv_id in self._udp_sender_receivers.get(rid, []):
                    ut = self._udp_t.get(recv_id, {}).get(rid, [])
                    ui = bisect.bisect_right(ut, t) - 1
                    if ui >= 0 and (best_t is None or ut[ui] > best_t):
                        best_t = ut[ui]
                        best_pose = self._udp_poses[recv_id][rid][ui]
                if best_pose is not None:
                    x, y, _ = best_pose
                    pts.append((x, y))
        return pts

    def _team_spacing_in_range(self, t0: float, t1: float, n_samples: int = 10) -> dict[str, Any] | None:
        """Sample team formation metrics over [t0, t1] and return averages."""
        if not self.robot_ids:
            return None
        duration = max(0.0, t1 - t0)
        if duration < 1e-6:
            times = [t0]
        else:
            step = duration / max(1, n_samples - 1)
            times = [t0 + i * step for i in range(n_samples)]

        cx_l, cy_l, w_l, d_l, dist_l, fwd_l = [], [], [], [], [], []
        for t in times:
            pts = self._robots_at_t(t)
            n = len(pts)
            if n < 1:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            cx_l.append(sum(xs) / n)
            cy_l.append(sum(ys) / n)
            if n >= 2:
                w_l.append(max(xs) - min(xs))
                d_l.append(max(ys) - min(ys))
                pair_dists = [
                    math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
                    for i in range(n) for j in range(i + 1, n)
                ]
                dist_l.append(sum(pair_dists) / len(pair_dists))
            fwd_l.append(sum(1 for x, _ in pts if x > 0))

        if not cx_l:
            return None

        def _avg(lst: list[float]) -> float:
            return round(sum(lst) / len(lst), 2) if lst else 0.0

        return {
            'centroid_x':  _avg(cx_l),
            'centroid_y':  _avg(cy_l),
            'width':       _avg(w_l),
            'depth':       _avg(d_l),
            'avg_dist':    _avg(dist_l),
            'fwd_count':   round(_avg(fwd_l), 1),
            'robot_count': len(self.robot_ids),
        }

    def segment_stats(
        self,
        t0: float,
        t1: float,
        possession_dist_m: float = 0.5,
        possession_hold_s: float = 0.1,
    ) -> dict[str, Any]:
        start, end = self._clamp_range(t0, t1)
        duration = max(0.0, end - start)

        robot_stats = [
            self._robot_stats_in_range(rid, start, end)
            for rid in self.robot_ids
        ]
        active_robot_count = sum(
            1 for stat in robot_stats
            if stat["has_pose_data"] or stat["kick_count"] > 0 or stat["fall_count"] > 0
        )
        total_distance_m = sum(stat["distance_m"] for stat in robot_stats)
        total_kick_count = sum(stat["kick_count"] for stat in robot_stats)
        total_fall_count = sum(stat["fall_count"] for stat in robot_stats)
        max_robot_speed_mps = max((stat["max_speed_mps"] for stat in robot_stats), default=0.0)

        return {
            "t0": round(start, 3),
            "t1": round(end, 3),
            "duration": round(duration, 3),
            "active_robot_count": active_robot_count,
            "robot_count": len(self.robot_ids),
            "total_distance_m": round(total_distance_m, 3),
            "total_kick_count": total_kick_count,
            "total_fall_count": total_fall_count,
            "max_robot_speed_mps": round(max_robot_speed_mps, 3),
            "robot_stats": robot_stats,
            "possession": self.possession_stats(start, end, possession_dist_m, possession_hold_s),
            "team_spacing": self._team_spacing_in_range(start, end),
        }

    def possession_preload(
        self,
        control_dist_m: float = 0.5,
        sample_hz: float = 2.0,
    ) -> dict[str, Any]:
        """Return time-sampled possession states for client-side timeline chart.

        State codes: 0=loose, 1=our, 2=enemy, 3=stuck.
        """
        if not self._ball_t or self.duration < 1e-6:
            return {"samples": [], "half_split": None, "enemy_tracked": False}

        _BALL_STALE_S = 1.0
        _CTRL = max(0.05, control_dist_m)
        enemy_tracked = bool(self._enemy_t)
        step = 1.0 / max(0.5, sample_hz)
        samples: list[list] = []

        t = 0.0
        while t <= self.duration + 1e-9:
            bi = bisect.bisect_right(self._ball_t, t) - 1
            if bi >= 0 and (t - self._ball_t[bi]) <= _BALL_STALE_S:
                bx, by = self._ball_xy[bi]

                min_our = float('inf')
                for rid in self.robot_ids:
                    pt = self._pose_t.get(rid, [])
                    ps = self._poses.get(rid, [])
                    if not pt:
                        continue
                    pi = bisect.bisect_right(pt, t) - 1
                    if pi < 0:
                        continue
                    rx, ry, _ = ps[pi]
                    d = math.hypot(rx - bx, ry - by)
                    if d < min_our:
                        min_our = d

                min_enemy = float('inf')
                if enemy_tracked:
                    ei = bisect.bisect_right(self._enemy_t, t) - 1
                    if ei >= 0:
                        for ex, ey in self._enemy_groups[ei]:
                            d = math.hypot(ex - bx, ey - by)
                            if d < min_enemy:
                                min_enemy = d

                our_near = min_our < _CTRL
                enemy_near = min_enemy < _CTRL
                if our_near and enemy_near:
                    state = 3
                elif our_near:
                    state = 1
                elif enemy_near:
                    state = 2
                else:
                    state = 0
                samples.append([round(t, 2), state])

            t += step

        half_split: float | None = None
        prev_fh: bool | None = None
        for t_rel, gc in zip(self._gc_t, self._gc_states):
            fh = gc.get('first_half', True)
            if prev_fh is True and not fh:
                half_split = round(t_rel, 3)
                break
            prev_fh = fh

        return {
            "samples": samples,
            "half_split": half_split,
            "enemy_tracked": enemy_tracked,
        }

    def gc_team_numbers(self) -> list[int]:
        """Return sorted unique team numbers seen in GC messages."""
        nums: set[int] = set()
        for gc in self._gc_states:
            for tm in gc.get("teams", []) or []:
                team_number = int(tm.get("team_number", 0) or 0)
                if team_number > 0:
                    nums.add(team_number)
        return sorted(nums)

    def game_summary(
        self,
        possession_dist_m: float = 0.5,
        possession_hold_s: float = 0.1,
    ) -> dict[str, Any]:
        """Return full-game and per-half segment stats for the summary panel."""
        half_split: float | None = None
        prev_fh: bool | None = None
        for t_rel, gc in zip(self._gc_t, self._gc_states):
            fh = gc.get('first_half', True)
            if prev_fh is True and not fh:
                half_split = round(t_rel, 3)
                break
            prev_fh = fh

        kw = dict(possession_dist_m=possession_dist_m, possession_hold_s=possession_hold_s)
        full_game   = self.segment_stats(0.0, self.duration, **kw)
        first_half  = self.segment_stats(0.0, half_split, **kw) if half_split is not None else None
        second_half = self.segment_stats(half_split, self.duration, **kw) if half_split is not None else None

        return {
            "half_split": half_split,
            "full_game": full_game,
            "first_half": first_half,
            "second_half": second_half,
        }

    def event_bookmarks(self) -> list[dict[str, Any]]:
        """Return condensed timeline events for bookmark/marker rendering."""
        events: list[dict[str, Any]] = []

        prev_state: int | None = None
        prev_set_play: int | None = None
        prev_scores: dict[int, int] = {}
        for t_rel, gc in zip(self._gc_t, self._gc_states):
            state = int(gc.get("state", -1))
            if prev_state is None or state != prev_state:
                events.append({
                    "t": round(t_rel, 3),
                    "kind": "state",
                    "state": state,
                })
                prev_state = state

            set_play = int(gc.get("set_play", 0) or 0)
            if prev_set_play is None:
                prev_set_play = set_play
            elif set_play != prev_set_play:
                events.append({
                    "t": round(t_rel, 3),
                    "kind": "setplay",
                    "set_play": set_play,
                })
                prev_set_play = set_play

            for tm in gc.get("teams", []) or []:
                team_number = int(tm.get("team_number", 0) or 0)
                score = int(tm.get("score", 0) or 0)
                if team_number <= 0:
                    continue
                prev_score = prev_scores.get(team_number)
                if prev_score is not None and score > prev_score:
                    events.append({
                        "t": round(t_rel, 3),
                        "kind": "goal",
                        "team_number": team_number,
                        "score": score,
                    })
                prev_scores[team_number] = score

        for rid in self.robot_ids:
            bt_times = self._bt_t.get(rid, [])
            bt_nodes = self._bt.get(rid, [])

            prev_kick = False
            for t_rel, node in zip(bt_times, bt_nodes):
                node_str = str(node or "").strip()
                is_kick = "kick" in node_str.lower()
                if is_kick and not prev_kick:
                    events.append({
                        "t": round(t_rel, 3),
                        "kind": "kick",
                        "robot_id": rid,
                    })
                prev_kick = is_kick

        for rid in self.robot_ids:
            lifted_times = self._lifted_t.get(rid, [])
            lifted_values = self._lifted.get(rid, [])

            prev_lifted = False
            for t_rel, lifted in zip(lifted_times, lifted_values):
                is_lifted = bool(lifted)
                if is_lifted and not prev_lifted:
                    events.append({
                        "t": round(t_rel, 3),
                        "kind": "fall",
                        "robot_id": rid,
                    })
                prev_lifted = is_lifted

        kind_order = {"state": 0, "setplay": 1, "goal": 2, "fall": 3, "kick": 4}
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for event in sorted(
            events,
            key=lambda e: (
                e["t"],
                kind_order.get(str(e.get("kind")), 99),
                int(e.get("robot_id", 0) or 0),
            ),
        ):
            if float(event["t"]) < 0.0:
                continue
            key = (
                event["t"],
                event.get("kind"),
                event.get("robot_id"),
                event.get("team_number"),
                event.get("score"),
                event.get("state"),
                event.get("set_play"),
                event.get("bt_node"),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(event)
        return deduped


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_GC_STATE_READY = 1

# Topic keys after _strip_robot_prefix() — support new (/robocup/ prefix) and bare (no prefix).
_KEY_POSE       = {'robocup/localization/pose',              'localization/pose'}
_KEY_DEST       = {'robocup/destination',                    'destination'}
_KEY_BT         = {'robocup/current_bt_node',                'current_bt_node'}
_KEY_LIFTED     = {'robocup/lifted',                         'lifted'}
_KEY_DETECT     = {'robocup/detected_objects',               'detected_objects'}
_KEY_UDP        = {'robocup/udp/data',                       'udp/data'}
_KEY_ENEMIES    = {'robocup/cooperative_perception/enemies', 'cooperative_perception/enemies'}
_KEY_GC         = {'robocup/game_control_data',              'game_control_data'}
_KEY_VEL_CMD    = {'robocup/rl_vel_cmd',                     'rl_vel_cmd'}


def _find_ready_ts(
    gc_samples: list[tuple[int, dict[str, Any]]],
) -> int | None:
    """Return the timestamp (ns) of the first *first-half* GC READY sample, or None.

    Second-half READY events (first_half=False) are intentionally excluded so that
    files recorded in the second half do not get anchored to t=0.  They fall through
    to wall-clock alignment via _estimate_sync_offset_from_gc / global_1h_anchor.
    """
    for ts, sample in gc_samples:
        if int(sample.get("state", -1)) == _GC_STATE_READY and sample.get("first_half", True):
            return ts
    return None


def _extract_gc_sync_samples(
    file_raw: list[tuple[int, str, str, bytes]],
    cls_fn,
) -> list[tuple[int, dict[str, Any]]]:
    """Extract deduplicated GC snapshots for cross-file time alignment."""
    out: list[tuple[int, dict[str, Any]]] = []
    prev_key: tuple[Any, ...] | None = None

    for ts, topic, type_str, data in sorted(file_raw, key=lambda m: m[0]):
        if _strip_robot_prefix(topic) not in _KEY_GC:
            continue
        try:
            msg = deserialize_message(data, cls_fn(type_str))
        except Exception:
            continue

        teams = tuple(
            sorted(
                (int(tm.team_number), int(tm.score))
                for tm in (msg.teams or [])
            )
        )
        sample = {
            "state": int(msg.state),
            "game_phase": int(msg.game_phase),
            "first_half": bool(msg.first_half),
            "set_play": int(msg.set_play),
            "kicking_team": int(msg.kicking_team),
            "secs_remaining": int(msg.secs_remaining),
            "secondary_time": int(msg.secondary_time),
            "stopped": int(msg.stopped),
            "teams": teams,
        }
        sample_key = (
            sample["state"],
            sample["game_phase"],
            sample["first_half"],
            sample["set_play"],
            sample["kicking_team"],
            sample["secs_remaining"],
            sample["secondary_time"],
            sample["stopped"],
            sample["teams"],
        )
        if sample_key == prev_key:
            continue
        prev_key = sample_key
        out.append((ts, sample))

    return out


def _gc_sync_lookup_keys(sample: dict[str, Any]) -> list[tuple[str, tuple[Any, ...]]]:
    """Return progressively looser keys for matching a GC sample across files."""
    return [
        (
            "strict",
            (
                sample["first_half"],
                sample["state"],
                sample["secs_remaining"],
                sample["secondary_time"],
                sample["set_play"],
                sample["stopped"],
                sample["game_phase"],
                sample["teams"],
            ),
        ),
        (
            "with_secondary",
            (
                sample["first_half"],
                sample["state"],
                sample["secs_remaining"],
                sample["secondary_time"],
                sample["set_play"],
                sample["stopped"],
            ),
        ),
        (
            "state_clock",
            (
                sample["first_half"],
                sample["state"],
                sample["secs_remaining"],
                sample["set_play"],
            ),
        ),
        (
            "state_only_clock",
            (
                sample["first_half"],
                sample["state"],
                sample["secs_remaining"],
            ),
        ),
        (
            "clock_only",
            (
                sample["first_half"],
                sample["secs_remaining"],
            ),
        ),
    ]


def _build_gc_reference_maps(
    per_file_gc_samples: list[list[tuple[int, dict[str, Any]]]],
    ready_ts_per_file: list[int | None],
) -> dict[str, dict[tuple[Any, ...], list[float]]]:
    """Build READY-anchored reference timeline indices from files that saw READY."""
    ref_maps: dict[str, dict[tuple[Any, ...], list[float]]] = {
        "strict": {},
        "with_secondary": {},
        "state_clock": {},
        "state_only_clock": {},
        "clock_only": {},
    }

    for gc_samples, ready_ts in zip(per_file_gc_samples, ready_ts_per_file):
        if ready_ts is None:
            continue
        for ts, sample in gc_samples:
            t_rel = (ts - ready_ts) / 1e9
            for level, key in _gc_sync_lookup_keys(sample):
                ref_maps[level].setdefault(key, []).append(t_rel)

    for level_map in ref_maps.values():
        for values in level_map.values():
            values.sort()

    return ref_maps


def _median_int(values: list[int]) -> int:
    values_sorted = sorted(values)
    return values_sorted[len(values_sorted) // 2]


def _estimate_sync_offset_from_gc(
    gc_samples: list[tuple[int, dict[str, Any]]],
    ref_maps: dict[str, dict[tuple[Any, ...], list[float]]],
) -> int | None:
    """Estimate the READY-relative raw timestamp offset for a file without READY."""
    if not gc_samples:
        return None

    def collect_candidates(
        samples: list[tuple[int, dict[str, Any]]],
    ) -> list[int]:
        candidates: list[int] = []
        for ts, sample in samples[:120]:
            for level, key in _gc_sync_lookup_keys(sample):
                matches = ref_maps[level].get(key)
                if not matches:
                    continue
                ref_t = matches[len(matches) // 2]
                candidates.append(ts - int(round(ref_t * 1e9)))
                break
        return candidates

    # Prefer PLAYING samples first because the match clock is most informative there.
    playing_samples = [
        (ts, sample)
        for ts, sample in gc_samples
        if int(sample.get("state", -1)) == 3
    ]
    candidates = collect_candidates(playing_samples)
    if not candidates:
        candidates = collect_candidates(gc_samples)
    if not candidates:
        return None
    return _median_int(candidates)


def load_session(file_paths: list[Path]) -> Session:
    _cls_cache: dict[str, type] = {}

    def cls(type_str: str) -> type:
        if type_str not in _cls_cache:
            _cls_cache[type_str] = get_message(type_str)
        return _cls_cache[type_str]

    # ── Step 1: Load raw messages per file ───────────────────────────────
    per_file_raw: list[list[tuple[int, str, str, bytes]]] = []
    for path in file_paths:
        file_raw: list[tuple[int, str, str, bytes]] = []
        try:
            reader = _open_reader(path)
        except (RuntimeError, ValueError) as exc:
            import logging
            logging.getLogger(__name__).warning("Skipping unreadable bag file %s: %s", path, exc)
            per_file_raw.append(file_raw)
            continue
        type_map = {t.name: t.type for t in reader.get_all_topics_and_types()}
        while reader.has_next():
            topic, data, ts = reader.read_next()
            if topic in type_map:
                file_raw.append((ts, topic, type_map[topic], data))
        per_file_raw.append(file_raw)

    if not any(per_file_raw):
        return Session()

    # ── Step 2: Extract per-file GC sync samples + READY timestamp ───────
    per_file_gc_samples: list[list[tuple[int, dict[str, Any]]]] = [
        _extract_gc_sync_samples(fr, cls) for fr in per_file_raw
    ]
    ready_ts_per_file: list[int | None] = [
        _find_ready_ts(gc_samples) for gc_samples in per_file_gc_samples
    ]
    global_start = min(
        (m[0] for fr in per_file_raw for m in fr), default=0
    )

    # ── Step 3: Compute per-file sync offset ─────────────────────────────
    # Files that saw a first-half READY keep t=0 at that READY timestamp.
    # Files that started later (e.g. robot swap / node restart) are aligned by
    # matching their GC progress (half/state/remaining time) against the
    # READY-anchored reference timeline from the files that did see READY.
    # Second-half-only files never get a first-half READY (ready_ts=None); GC
    # estimation also fails because the reference maps only contain first-half
    # entries.  In that case we fall back to global_1h_anchor (the minimum
    # first-half READY ns across all files), which places second-half data at
    # its correct wall-clock position relative to the first half.
    if any(ts is not None for ts in ready_ts_per_file):
        global_1h_anchor: int = min(ts for ts in ready_ts_per_file if ts is not None)
        ref_maps = _build_gc_reference_maps(
            per_file_gc_samples, ready_ts_per_file,
        )
        file_offsets: list[int] = []
        for i, ready_ts in enumerate(ready_ts_per_file):
            if ready_ts is not None:
                file_offsets.append(ready_ts)
            else:
                estimated = _estimate_sync_offset_from_gc(
                    per_file_gc_samples[i], ref_maps,
                )
                file_offsets.append(estimated if estimated is not None else global_1h_anchor)
    else:
        file_offsets = [global_start] * len(per_file_raw)

    # ── Step 4: Merge messages with adjusted relative time ───────────────
    # t < 0  → before READY;  t = 0  → READY;  t > 0  → after READY
    merged: list[tuple[float, str, str, bytes]] = []
    for i, file_raw in enumerate(per_file_raw):
        offset = file_offsets[i]
        for ts, topic, type_str, data in file_raw:
            merged.append(((ts - offset) / 1e9, topic, type_str, data))
    merged.sort(key=lambda m: m[0])

    # ── Step 5: Parse messages into Session ──────────────────────────────
    sess = Session()
    sess.start_ts_ns = min(
        (fr[0][0] for fr in per_file_raw if fr), default=0
    )

    latest_pose: dict[int, tuple[float, float, float]] = {}

    buf_pose:    dict[int, list] = {}
    buf_dest:    dict[int, list] = {}
    buf_bt:      dict[int, list] = {}
    buf_lifted:  dict[int, list] = {}
    buf_vel_cmd: dict[int, list] = {}
    buf_ball:    list[tuple[float, float, float]] = []
    buf_enemy:   list[tuple[float, list]] = []
    buf_gc:     list[tuple[float, dict]] = []

    buf_per_ball:   dict[int, list[tuple[float, float, float]]] = {}
    buf_per_detect: dict[int, list[tuple[float, list]]] = {}
    buf_udp: dict[int, dict[int, list[tuple[float, float, float, float]]]] = {}

    for t, topic, type_str, data in merged:
        rid = _robot_id_from_topic(topic)
        key = _strip_robot_prefix(topic)

        try:
            if key in _KEY_POSE:
                msg = deserialize_message(data, cls(type_str))
                if rid is not None:
                    latest_pose[rid] = (msg.x, msg.y, msg.theta)
                    buf_pose.setdefault(rid, []).append((t, msg.x, msg.y, msg.theta))

            elif key in _KEY_DEST:
                msg = deserialize_message(data, cls(type_str))
                if rid is not None:
                    buf_dest.setdefault(rid, []).append((t, msg.x, msg.y))

            elif key in _KEY_BT:
                msg = deserialize_message(data, cls(type_str))
                if rid is not None:
                    buf_bt.setdefault(rid, []).append((t, msg.data))

            elif key in _KEY_LIFTED:
                msg = deserialize_message(data, cls(type_str))
                if rid is not None:
                    buf_lifted.setdefault(rid, []).append((t, bool(msg.data)))

            elif key in _KEY_DETECT:
                msg = deserialize_message(data, cls(type_str))
                if rid is not None and rid in latest_pose:
                    rx, ry, rth = latest_pose[rid]
                    ball_g: tuple[float, float] | None = None
                    others_g: list[tuple[float, float]] = []

                    for obj in msg.data:
                        gx, gy = _local_to_global(rx, ry, rth, obj.pos.x, obj.pos.y)
                        if obj.name == 'ball':
                            ball_g = (gx, gy)
                        elif obj.name in ('ally', 'robot'):
                            if not (gx == 0.0 and gy == 0.0):
                                others_g.append((gx, gy, obj.name))

                    if ball_g:
                        buf_ball.append((t, ball_g[0], ball_g[1]))
                        buf_per_ball.setdefault(rid, []).append((t, ball_g[0], ball_g[1]))
                    if others_g:
                        buf_per_detect.setdefault(rid, []).append((t, others_g))

            elif key in _KEY_UDP:
                msg = deserialize_message(data, cls(type_str))
                if rid is not None:
                    pid = int(msg.current_pose.player_id)
                    if pid > 0:
                        x = msg.current_pose.position.x
                        y = msg.current_pose.position.y
                        theta = msg.current_pose.position.theta
                        if not (x == 0.0 and y == 0.0):
                            (buf_udp
                             .setdefault(rid, {})
                             .setdefault(pid, [])
                             .append((t, x, y, theta)))

            elif key in _KEY_ENEMIES:
                msg = deserialize_message(data, cls(type_str))
                group = [(obs.position.x, obs.position.y)
                         for obs in msg.observations
                         if not (obs.position.x == 0.0 and obs.position.y == 0.0)]
                if group:
                    buf_enemy.append((t, group))

            elif key in _KEY_GC:
                msg = deserialize_message(data, cls(type_str))
                teams_info = [
                    {"team_number": int(tm.team_number), "score": int(tm.score)}
                    for tm in msg.teams
                ] if msg.teams else []
                buf_gc.append((t, {
                    "state": int(msg.state),
                    "game_phase": int(msg.game_phase),
                    "first_half": bool(msg.first_half),
                    "set_play": int(msg.set_play),
                    "kicking_team": int(msg.kicking_team),
                    "secs_remaining": int(msg.secs_remaining),
                    "secondary_time": int(msg.secondary_time),
                    "stopped": int(msg.stopped),
                    "teams": teams_info,
                }))

            elif key in _KEY_VEL_CMD:
                msg = deserialize_message(data, cls(type_str))
                if rid is not None and len(msg.data) >= 2:
                    buf_vel_cmd.setdefault(rid, []).append(
                        (t, float(msg.data[0]), float(msg.data[1]))
                    )

        except Exception:
            continue

    # ── Step 6: Commit buffers → Session ─────────────────────────────────
    for rid, lst in buf_pose.items():
        sess._pose_t[rid]  = [e[0] for e in lst]
        sess._poses[rid]   = [(e[1], e[2], e[3]) for e in lst]
    for rid, lst in buf_dest.items():
        sess._dest_t[rid]  = [e[0] for e in lst]
        sess._dests[rid]   = [(e[1], e[2]) for e in lst]
    for rid, lst in buf_bt.items():
        sess._bt_t[rid]    = [e[0] for e in lst]
        sess._bt[rid]      = [e[1] for e in lst]
    for rid, lst in buf_lifted.items():
        sess._lifted_t[rid]  = [e[0] for e in lst]
        sess._lifted[rid]    = [e[1] for e in lst]
    for rid, lst in buf_vel_cmd.items():
        sess._vel_cmd_t[rid] = [e[0] for e in lst]
        sess._vel_cmds[rid]  = [(e[1], e[2]) for e in lst]

    buf_ball.sort(key=lambda e: e[0])
    sess._ball_t  = [e[0] for e in buf_ball]
    sess._ball_xy = [(e[1], e[2]) for e in buf_ball]

    buf_enemy.sort(key=lambda e: e[0])
    sess._enemy_t      = [e[0] for e in buf_enemy]
    sess._enemy_groups = [e[1] for e in buf_enemy]

    buf_gc.sort(key=lambda e: e[0])
    sess._gc_t      = [e[0] for e in buf_gc]
    sess._gc_states = [e[1] for e in buf_gc]

    for rid, lst in buf_per_ball.items():
        sess._per_ball_t[rid]  = [e[0] for e in lst]
        sess._per_ball_xy[rid] = [(e[1], e[2]) for e in lst]
    for rid, lst in buf_per_detect.items():
        sess._per_detect_t[rid]    = [e[0] for e in lst]
        sess._per_detect_objs[rid] = [e[1] for e in lst]

    for recv_id, senders in buf_udp.items():
        sess._udp_t[recv_id]     = {}
        sess._udp_poses[recv_id] = {}
        for sender_id, lst in senders.items():
            sess._udp_t[recv_id][sender_id]     = [e[0] for e in lst]
            sess._udp_poses[recv_id][sender_id] = [(e[1], e[2], e[3]) for e in lst]
            sess._udp_sender_receivers.setdefault(sender_id, []).append(recv_id)

    # Include robots with position records in udp/data even if they lack localization/pose data
    udp_only_ids = set(sess._udp_sender_receivers) - set(sess._pose_t)
    sess.robot_ids = sorted(set(sess._pose_t) | udp_only_ids)
    ends = ([v[-1] for v in sess._pose_t.values() if v]
            + ([sess._ball_t[-1]] if sess._ball_t else [])
            + ([sess._gc_t[-1]]   if sess._gc_t   else []))
    sess.duration = max(ends) if ends else 0.0

    return sess
