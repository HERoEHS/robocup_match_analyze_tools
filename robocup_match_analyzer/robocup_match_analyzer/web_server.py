"""FastAPI web server for robocup_match_analyzer."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import functools
import logging
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
)

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware

from robocup_match_analyzer.mcap_merger import (
    create_download_zip,
    merge_bags,
    suggest_merged_name,
)
from robocup_match_analyzer.mcap_loader import Session, load_session


_FIELD_CONFIG: dict[str, Any] = {
    "length_m": 14.0,
    "width_m": 9.0,
    "border_strip_m": 1.0,
    "center_circle_r_m": 1.5,
    "goal_area": {"depth_m": 1.0, "width_m": 4.0},
    "penalty_area": {"depth_m": 3.0, "width_m": 6.0},
    "penalty_mark_distance_m": 2.0,
    "goal": {"depth_m": 0.7, "inner_width_m": 2.4},
}


@dataclass
class LoadedSession:
    session: Session
    files: list[Path]
    merged_name: str


def _file_size(p: Path) -> int:
    """Return size of a file or rosbag2 directory package."""
    if p.is_dir():
        return sum(f.stat().st_size for f in p.rglob('*') if f.is_file())
    return p.stat().st_size


def _discover_files(data_dir: Path) -> dict[str, Any]:
    """Scan data_dir and its immediate subdirectories for .mcap files.

    Returns groups sorted by most recent file mtime (newest first).
    Each group = one directory that contains .mcap files.
    """
    if not data_dir.exists():
        return {"data_dir": str(data_dir), "groups": []}

    def _make_file_entry(f: Path) -> dict[str, Any]:
        rm = re.match(r'^(?:robocup_|robot)(\d+)_', f.name)
        return {
            "path": str(f),
            "name": f.name,
            "robot_id": int(rm.group(1)) if rm else None,
            "size_bytes": _file_size(f),
            "mtime": f.stat().st_mtime,
        }

    raw_groups: list[dict[str, Any]] = []

    # data_dir itself
    direct = sorted(data_dir.glob('*.mcap'))
    if direct:
        raw_groups.append({
            "dir": data_dir.name,
            "dir_path": str(data_dir),
            "files": [_make_file_entry(f) for f in direct],
        })

    # immediate subdirectories
    for subdir in sorted(data_dir.iterdir()):
        if not subdir.is_dir():
            continue
        mcaps = sorted(subdir.glob('*.mcap'))
        if not mcaps:
            continue
        raw_groups.append({
            "dir": subdir.name,
            "dir_path": str(subdir),
            "files": [_make_file_entry(f) for f in mcaps],
        })

    raw_groups.sort(
        key=lambda g: max(f["mtime"] for f in g["files"]),
        reverse=True,
    )
    return {"data_dir": str(data_dir), "groups": raw_groups}


def create_app(data_dir: Path, static_dir: Path, our_team_number: int = 0) -> FastAPI:
    app = FastAPI(title="RoboCup Match Analyzer")
    _sessions: dict[str, LoadedSession] = {}
    _state: dict[str, Any] = {"data_dir": data_dir, "our_team_number": our_team_number}

    def _get_loaded_session(session_key: str) -> LoadedSession:
        record = _sessions.get(session_key)
        if record is None:
            raise HTTPException(status_code=404, detail="세션 미로드. /api/load 먼저 호출")
        return record

    def _cleanup_temp_tree(path: Path) -> None:
        shutil.rmtree(path, ignore_errors=True)

    class _NoCacheMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            p = request.url.path
            if p.startswith('/api/'):
                logging.info('→ %s %s', request.method, p)
            _t = time.monotonic()
            resp = await call_next(request)
            if p.startswith('/api/'):
                logging.info('← %s %s %d (%.2fs)', request.method, p, resp.status_code, time.monotonic() - _t)
            if p.startswith('/js/') or p.startswith('/css/') or p in ('/', '') or p.endswith('.html'):
                resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            return resp

    app.add_middleware(_NoCacheMiddleware)

    # ── API ──────────────────────────────────────────────────────────────

    @app.get('/api/field_config')
    async def api_field_config() -> dict[str, Any]:
        return dict(_FIELD_CONFIG)

    @app.get('/api/data_dir')
    async def api_get_data_dir() -> dict[str, Any]:
        return {"data_dir": str(_state["data_dir"])}

    @app.get('/api/team_config')
    async def api_get_team_config() -> dict[str, Any]:
        current = _sessions.get(list(_sessions)[-1]) if _sessions else None
        team_numbers = current.session.gc_team_numbers() if current else []
        return {
            "our_team_number": _state["our_team_number"],
            "team_numbers": team_numbers,
        }

    @app.post('/api/team_config')
    async def api_set_team_config(body: dict[str, Any]) -> dict[str, Any]:
        num = int(body.get('our_team_number', 0) or 0)
        _state["our_team_number"] = num
        return {"our_team_number": num}

    @app.post('/api/data_dir')
    async def api_set_data_dir(body: dict[str, Any]) -> dict[str, Any]:
        """Change the data directory and return the new session list."""
        raw = body.get('path', '').strip()
        if not raw:
            raise HTTPException(status_code=400, detail="path 필드가 비어 있음")
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"디렉토리 없음: {path}")
        if not path.is_dir():
            raise HTTPException(status_code=400, detail=f"디렉토리가 아님: {path}")
        _state["data_dir"] = path
        return _discover_files(path)

    @app.get('/api/sessions')
    async def api_sessions() -> dict[str, Any]:
        return _discover_files(_state["data_dir"])

    @app.post('/api/load')
    async def api_load(body: dict[str, Any]) -> dict[str, Any]:
        """Load an explicit list of bag paths."""
        file_list: list[str] = body.get('files', [])
        if not file_list:
            raise HTTPException(status_code=400, detail="files 필드가 비어 있음")

        paths = [Path(f).expanduser().resolve() for f in file_list]
        missing = [str(p) for p in paths if not p.exists()]
        if missing:
            raise HTTPException(status_code=404, detail=f"파일 없음: {missing}")

        import hashlib, json
        session_key = hashlib.md5(json.dumps(sorted(file_list)).encode()).hexdigest()[:12]

        logging.info('[api/load] 시작: %d개 파일', len(paths))
        t0 = time.monotonic()
        loop = asyncio.get_running_loop()
        sess = await loop.run_in_executor(None, functools.partial(load_session, paths))
        logging.info('[api/load] load_session 완료: %.2fs, robots=%s', time.monotonic() - t0, sess.robot_ids)
        _sessions[session_key] = LoadedSession(
            session=sess,
            files=paths,
            merged_name=suggest_merged_name(paths),
        )

        team_numbers = sess.gc_team_numbers()
        if _state["our_team_number"] == 0 and len(team_numbers) == 1:
            _state["our_team_number"] = team_numbers[0]

        raw_gaps = sess.robot_data_gaps(gap_threshold_s=1.0)
        result = {
            "session_key": session_key,
            "duration": round(sess.duration, 3),
            "robot_ids": sess.robot_ids,
            "game_state_events": sess.game_state_events(),
            "event_bookmarks": sess.event_bookmarks(),
            "segment_presets": sess.segment_presets(),
            "segments": sess.segment_presets(),
            "summary": sess.game_summary(),
            "team_numbers": team_numbers,
            "our_team_number": _state["our_team_number"],
            "robot_gaps": {str(rid): gaps for rid, gaps in raw_gaps.items()},
        }
        logging.info('[api/load] 응답 전송 완료: total=%.2fs', time.monotonic() - t0)
        return result

    @app.get('/api/frame')
    async def api_frame(session_key: str, t: float) -> dict[str, Any]:
        return _get_loaded_session(session_key).session.frame_at(max(0.0, t))

    @app.get('/api/trail')
    async def api_trail(session_key: str, t: float, window: float = 15.0) -> dict[str, Any]:
        sess = _get_loaded_session(session_key).session
        return {"window": window, "robots": sess.trail(t, window)}

    @app.get('/api/heatmap')
    async def api_heatmap(
        session_key: str,
        player_id: str = 'all',
        t0: float = 0.0,
        t1: float | None = None,
    ) -> dict[str, Any]:
        sess = _get_loaded_session(session_key).session
        end = t1 if t1 is not None else sess.duration
        pid = None if player_id in ('all', '', 'null') else int(player_id)
        return sess.heatmap(pid, t0, end)

    @app.get('/api/heatmap_preload')
    async def api_heatmap_preload(session_key: str) -> dict[str, Any]:
        return _get_loaded_session(session_key).session.heatmap_preload()

    @app.get('/api/possession_preload')
    async def api_possession_preload(
        session_key: str,
        possession_dist_m: float = 0.5,
    ) -> dict[str, Any]:
        return _get_loaded_session(session_key).session.possession_preload(
            control_dist_m=possession_dist_m,
        )

    @app.get('/api/space_control_samples')
    async def api_space_control_samples(
        session_key: str,
        max_samples: int = 240,
    ) -> dict[str, Any]:
        sess = _get_loaded_session(session_key).session
        capped = max(16, min(max_samples, 600))
        return sess.space_control_samples(max_samples=capped)

    @app.get('/api/segment_stats')
    async def api_segment_stats(
        session_key: str,
        t0: float,
        t1: float,
        possession_dist_m: float = 0.5,
        possession_hold_s: float = 0.1,
    ) -> dict[str, Any]:
        sess = _get_loaded_session(session_key).session
        return sess.segment_stats(t0, t1, possession_dist_m, possession_hold_s)

    @app.get('/api/game_summary')
    async def api_game_summary(
        session_key: str,
        possession_dist_m: float = 0.5,
        possession_hold_s: float = 0.1,
    ) -> dict[str, Any]:
        sess = _get_loaded_session(session_key).session
        return sess.game_summary(possession_dist_m, possession_hold_s)

    @app.get('/api/download_merged')
    async def api_download_merged(session_key: str) -> FileResponse:
        record = _get_loaded_session(session_key)
        temp_root = Path(tempfile.mkdtemp(prefix='robocup_match_merge_', dir='/tmp'))
        bag_uri = temp_root / f'{record.merged_name}.mcap'
        zip_path = temp_root / f'{record.merged_name}.zip'

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, functools.partial(merge_bags, record.files, bag_uri)
            )
            create_download_zip(bag_uri, zip_path)
        except Exception as exc:
            _cleanup_temp_tree(temp_root)
            raise HTTPException(status_code=500, detail=f'병합 다운로드 생성 실패: {exc}')

        return FileResponse(
            path=zip_path,
            media_type='application/zip',
            filename=zip_path.name,
            background=BackgroundTask(_cleanup_temp_tree, temp_root),
        )

    # ── Static (must be last) ─────────────────────────────────────────────
    app.mount('/', StaticFiles(directory=str(static_dir), html=True), name='static')

    return app
