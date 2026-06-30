from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml
from ament_index_python.packages import get_package_share_directory


SCHEMA_VERSION = 1

_DEFAULT_FIELD: dict[str, Any] = {
    # HSL Humanoid Soccer League — M-Field (Medium) official nominal values
    # Source: HSL-Rules/rules/medium_field.tex (LaTeX drawing, nominal values)
    # Coordinate system: origin=field center, x ∈ [-7.0, +7.0], y ∈ [-4.5, +4.5]
    "length_m": 14.0,
    "width_m": 9.0,
    "origin": "center",
    "line_width_m": 0.05,
    "goal_line_width_m": 0.10,
    "border_strip_m": 1.0,
    "center_circle_r_m": 1.5,
    "goal_area":    {"depth_m": 1.0, "width_m": 4.0},
    "penalty_area": {"depth_m": 3.0, "width_m": 6.0},
    "penalty_mark_distance_m": 2.0,
    "penalty_mark_diameter_m": 0.1,
    "corner_arc_radius_m": 0.5,
    "goal": {
        "depth_m": 0.7,
        "inner_width_m": 2.4,
        "post_diameter_m": 0.1,
    },
}

# Design Ref: §changes/backend — defaults section default values
# Both global/local are required. Same schema as zone's action_policy (action/target/xy/note).
_DEFAULT_DEFAULTS: dict[str, Any] = {
    "global": {
        "action": "dribble",
        "target": "destination",
        "xy": "1;0",
        "note": "Global fallback — used when no global zone matches",
    },
    "local": {
        "action": "dribble",
        "target": "destination",
        "xy": "1;0",
        "note": "Local fallback — used when no local zone matches",
    },
}


_REL_SOURCE_FROM_WS_SRC = (
    "robocup_match_analyze_tools", "robocup_realtime_monitoring", "config", "strategy_zones.yaml",
)


def _share_yaml_path() -> Path:
    """yaml path under the share directory as reported by ament_index. For fallback use. May throw."""
    share = Path(get_package_share_directory("robocup_realtime_monitoring"))
    return share / "config" / "strategy_zones.yaml"


def _try_locate_source_from_share(share_path: Path) -> Path | None:
    """Back-trace the workspace root from the share path (.../install/<pkg>/share/<pkg>)
    and infer the source yaml path under src. Returns None on failure. Does not throw."""
    try:
        parts = share_path.parts
        if len(parts) < 5:
            return None
        if parts[-2] != "share" or parts[-4] != "install":
            return None
        ws = Path(*parts[:-4])
        candidate = ws / "src" / Path(*_REL_SOURCE_FROM_WS_SRC)
        # Return the path even if the file doesn't exist — the first Save can create it there.
        return candidate
    except Exception:
        return None


def _locate_source_yaml() -> tuple[Path, str]:
    """Determine the absolute path of the single-source-of-truth yaml. Returns (path, reason_string).

    No mkdir at any step. Does not throw.

    **R-8: Home directory fallback completely removed**.
    The old emergency fallback was the cause of the R-3 channel split regression.
    This function now never returns a home directory path — on total failure it falls back
    to the share path (which may be read-only, causing Save to fail).
    Users are recommended to set the env variable explicitly or use --symlink-install.
    """
    # 1) env ROBOCUP_STRATEGY_ZONES_PATH (forced absolute path)
    try:
        env_explicit = os.environ.get("ROBOCUP_STRATEGY_ZONES_PATH", "").strip()
        if env_explicit:
            return Path(env_explicit).expanduser().resolve(), "env:ROBOCUP_STRATEGY_ZONES_PATH"
    except Exception:
        pass

    # 2) env ROBOCUP_WS_SRC → direct src path
    try:
        ws_src = os.environ.get("ROBOCUP_WS_SRC", "").strip()
        if ws_src:
            candidate = Path(ws_src).expanduser().resolve() / Path(*_REL_SOURCE_FROM_WS_SRC)
            return candidate, "env:ROBOCUP_WS_SRC"
    except Exception:
        pass

    # 3) ament_index share back-trace
    share_yaml: Path | None = None
    try:
        share_yaml = _share_yaml_path()
    except Exception as e:
        print(
            f"[robocup_strategy_gui][zone_store] WARN: ament_index lookup failed: {e!r} — "
            "check that the robocup_realtime_monitoring package is installed and the env is sourced.",
            file=sys.stderr,
        )

    if share_yaml is not None:
        src_guess = _try_locate_source_from_share(share_yaml.parent.parent)
        if src_guess is not None:
            return src_guess, "auto:share back-trace"
        # 4) fallback: share/.../config/strategy_zones.yaml + WARN (may be read-only, Save may fail)
        print(
            "[robocup_strategy_gui][zone_store] WARN: failed to infer source yaml location → using share yaml. "
            "This path may be read-only; GUI Save may fail. "
            "Recommended: env ROBOCUP_STRATEGY_ZONES_PATH=<absolute_src_yaml_path> or ROBOCUP_WS_SRC=<ws>/src.",
            file=sys.stderr,
        )
        return share_yaml, "fallback:share (read-only risk)"

    # 5) All steps failed — never fall back to home directory. Notify user with a clear error message.
    # Returning an empty path causes the caller to immediately see an error (both Save and Load will fail).
    print(
        "[robocup_strategy_gui][zone_store] ERROR: failed to determine yaml path — all fallbacks exhausted. "
        "Required: set env ROBOCUP_STRATEGY_ZONES_PATH explicitly (e.g. export ROBOCUP_STRATEGY_ZONES_PATH="
        "/home/chris24/robot_ws/src/robocup_match_analyze_tools/robocup_realtime_monitoring/config/strategy_zones.yaml).",
        file=sys.stderr,
    )
    return Path(""), "error:no-path (env must be set explicitly)"


def resolve_yaml_path(override: str | None = None) -> Path:
    """Absolute path of the yaml to edit/query. No home directory auto-copy or fallback.

    - If override (launch param `zones_path`) is given, that path is used unconditionally.
    - Otherwise determined by the priority order of _locate_source_yaml().
    - In neither case is the file pre-created or copied.
    - **R-8: Home directory fallback completely removed**. Does not throw either —
      on total failure returns an empty path → caller (save_zones/load_zones) surfaces a clear error to the user.
    """
    if override:
        try:
            return Path(override).expanduser().resolve()
        except Exception:
            return Path(override)
    try:
        path, source = _locate_source_yaml()
        print(f"[robocup_strategy_gui][zone_store] yaml path resolved: {path} (source={source})")
        return path
    except Exception as e:
        # _locate_source_yaml is designed not to throw, but guard against the unexpected.
        # Never fall back to home directory. Return empty path → clear error surfaced to user.
        print(
            f"[robocup_strategy_gui][zone_store] CRITICAL: _locate_source_yaml raised: {e!r} — "
            "cannot determine yaml path. Set env ROBOCUP_STRATEGY_ZONES_PATH explicitly.",
            file=sys.stderr,
        )
        return Path("")


# ─── Validation ───────────────────────────────────────────────────────────

_VALID_TYPES = {"rect", "circle"}
_VALID_SPACES = {"global", "local"}
_VALID_ACTIONS = {"none", "dribble", "kick", "pass", "move_to", "turn_to"}


def _validate_geometry(ztype: str, geom: dict[str, Any]) -> None:
    if ztype == "rect":
        for k in ("x1", "y1", "x2", "y2"):
            if k not in geom:
                raise ValueError(f"rect zone missing '{k}'")
            if not isinstance(geom[k], (int, float)):
                raise ValueError(f"rect zone '{k}' is not a number: {geom[k]!r}")
    elif ztype == "circle":
        for k in ("cx", "cy", "r"):
            if k not in geom:
                raise ValueError(f"circle zone missing '{k}'")
        if geom["r"] <= 0:
            raise ValueError(f"circle zone radius is <= 0: {geom['r']}")


def _normalize_action_policy(ap: Any, ctx: str) -> dict[str, Any]:
    """Validate and normalize an action_policy dict. Shared by zones and defaults."""
    if ap is None:
        ap = {"action": "none"}
    if not isinstance(ap, dict):
        raise ValueError(f"{ctx}.action_policy is not a dict")
    act = ap.get("action", "none")
    if act not in _VALID_ACTIONS:
        raise ValueError(f"{ctx}.action_policy.action is invalid: {act}")
    out: dict[str, Any] = {"action": act}
    for opt in ("target", "xy", "note"):
        if opt in ap and ap[opt] not in (None, ""):
            out[opt] = ap[opt]
    return out


def _normalize_defaults(raw: Any) -> dict[str, Any]:
    """Validate and normalize the defaults section."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("defaults is not a dict")
    out: dict[str, Any] = {}
    for space in ("global", "local"):
        space_raw = raw.get(space)
        if space_raw is None:
            out[space] = dict(_DEFAULT_DEFAULTS[space])
        else:
            out[space] = _normalize_action_policy(space_raw, f"defaults.{space}")
    return out


def validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the API input dict. Raises ValueError on failure."""
    if not isinstance(payload, dict):
        raise ValueError("payload is not a dict")

    version = payload.get("version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema version: {version}")

    field = dict(_DEFAULT_FIELD)
    defaults = _normalize_defaults(payload.get("defaults"))
    zones = payload.get("zones", [])
    if not isinstance(zones, list):
        raise ValueError("zones is not a list")

    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for idx, z in enumerate(zones):
        if not isinstance(z, dict):
            raise ValueError(f"zones[{idx}] is not a dict")
        zid = str(z.get("id") or "").strip()
        if not zid:
            raise ValueError(f"zones[{idx}].id is missing")
        if zid in seen_ids:
            raise ValueError(f"Duplicate zone id: {zid}")
        seen_ids.add(zid)

        ztype = z.get("type")
        if ztype not in _VALID_TYPES:
            raise ValueError(f"zone '{zid}'.type is invalid: {ztype} (rect|circle)")

        space = z.get("space", "global")
        if space not in _VALID_SPACES:
            raise ValueError(f"zone '{zid}'.space is invalid: {space} (global|local)")

        geom = z.get("geometry") or {}
        _validate_geometry(ztype, geom)

        action_policy = _normalize_action_policy(
            z.get("action_policy"), f"zone '{zid}'",
        )

        if "note" in (z.get("action_policy") or {}):
            action_policy.setdefault("note", z["action_policy"]["note"])

        normalized.append({
            "id": zid,
            "name": z.get("name") or zid,
            "type": ztype,
            "space": space,
            "geometry": geom,
            "action_policy": action_policy,
            "bt_ref": z.get("bt_ref", ""),
            "color": z.get("color", "#3498db"),
        })

    return {
        "version": SCHEMA_VERSION,
        "field": field,
        "defaults": defaults,
        "zones": normalized,
    }


# ─── Migration ────────────────────────────────────────────────────────────

_KICK_CORRIDOR_SEED_GEOM = {"x1": 5.5, "y1": -1.5, "x2": 8.0, "y2": 1.5}
_KICK_CORRIDOR_SEED_AP = {
    "action": "kick", "target": "goal", "xy": "7.6;0",
}


def _geom_matches(a: dict[str, Any], b: dict[str, Any]) -> bool:
    keys = set(a.keys()) | set(b.keys())
    for k in keys:
        try:
            if abs(float(a.get(k, 0)) - float(b.get(k, 0))) > 1e-6:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _ap_matches(ap: dict[str, Any], seed: dict[str, Any]) -> bool:
    for k, v in seed.items():
        if str(ap.get(k, "")) != str(v):
            return False
    return True


def _migrate_kick_corridor(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Merge legacy goalkeeper_kick_corridor + attacker_center_kick into kick_corridor."""
    if not isinstance(raw, dict):
        return raw, []
    zones = raw.get("zones")
    if not isinstance(zones, list):
        return raw, []

    log: list[str] = []
    ids = {z.get("id"): i for i, z in enumerate(zones) if isinstance(z, dict)}
    if "kick_corridor" in ids:
        for old_id in ("goalkeeper_kick_corridor", "attacker_center_kick"):
            if old_id in ids:
                log.append(
                    f"마이그레이션: kick_corridor 가 이미 존재하므로 옛 '{old_id}' 는 제거"
                )
        new_zones = [z for z in zones if z.get("id") not in {"goalkeeper_kick_corridor", "attacker_center_kick"}]
        if len(new_zones) != len(zones):
            raw = dict(raw)
            raw["zones"] = new_zones
        return raw, log

    old_targets = [zid for zid in ("goalkeeper_kick_corridor", "attacker_center_kick") if zid in ids]
    if not old_targets:
        return raw, []

    seed_ok = True
    for zid in old_targets:
        z = zones[ids[zid]]
        if not _geom_matches(z.get("geometry") or {}, _KICK_CORRIDOR_SEED_GEOM):
            seed_ok = False
            log.append(
                f"마이그레이션 보류: '{zid}' geometry 가 시드와 다름 — 자동 통합하지 않음"
            )
        if not _ap_matches(z.get("action_policy") or {}, _KICK_CORRIDOR_SEED_AP):
            seed_ok = False
            log.append(
                f"마이그레이션 보류: '{zid}' action_policy 가 시드와 다름 — 자동 통합하지 않음"
            )

    if not seed_ok:
        return raw, log

    new_zones: list[dict[str, Any]] = []
    promoted = False
    for z in zones:
        zid = z.get("id") if isinstance(z, dict) else None
        if zid in ("goalkeeper_kick_corridor", "attacker_center_kick"):
            if not promoted:
                z = dict(z)
                z["id"] = "kick_corridor"
                z["name"] = "골 정면 킥 코리도"
                z["bt_ref"] = "OnBallCaptured/{Goalkeeper,Attacker}/KickCorridor"
                z["color"] = "#e74c3c"
                new_zones.append(z)
                promoted = True
                log.append(f"마이그레이션: '{zid}' → 'kick_corridor' 로 통합")
            else:
                log.append(f"마이그레이션: '{zid}' 제거 (kick_corridor 와 중복)")
        else:
            new_zones.append(z)
    raw = dict(raw)
    raw["zones"] = new_zones
    return raw, log


# ─── Disk I/O ─────────────────────────────────────────────────────────────

def load_zones(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": SCHEMA_VERSION,
            "field": dict(_DEFAULT_FIELD),
            "defaults": _normalize_defaults(None),
            "zones": [],
        }
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    raw, log_msgs = _migrate_kick_corridor(raw)
    for msg in log_msgs:
        print(f"[robocup_strategy_gui][zone_store] {msg}")

    return validate_payload(raw)


def save_zones(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_payload(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    # atomic write
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            normalized,
            f,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    os.replace(tmp, path)
    return normalized


def get_field_config() -> dict[str, Any]:
    """Return only the court dimensions needed for frontend bootstrap."""
    return dict(_DEFAULT_FIELD)
