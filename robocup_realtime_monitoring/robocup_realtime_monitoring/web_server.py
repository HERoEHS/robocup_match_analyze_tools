from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from robocup_realtime_monitoring import zone_store


# ─── R-5: Call /robocup_strategy/reload service immediately after PUT /api/zones ──────────
# Create only one rclpy node at module level and reuse it (avoid creating/destroying a node on every save).
# Fail-soft even if rclpy/std_srvs is unavailable or commander is not running.
# mtime polling acts as a backup with 100ms debounce — service failure is operationally harmless.
_RCLPY_AVAILABLE = True
try:
    import rclpy
    from rclpy.node import Node as _RclpyNode
    from std_srvs.srv import Trigger as _TriggerSrv
except Exception:  # Swallow all import/setup failures such as ImportError / OSError.
    _RCLPY_AVAILABLE = False

_reload_client_node: Any = None
_reload_client: Any = None


def _ensure_reload_client() -> bool:
    """Check if the global reload service client is ready. If not, attempt to create it. Failure is harmless."""
    global _reload_client_node, _reload_client
    if not _RCLPY_AVAILABLE:
        return False
    if _reload_client is not None:
        return True
    try:
        # Shares the context already initialised by rclpy.init() in main_web.py.
        if not rclpy.ok():
            return False
        _reload_client_node = _RclpyNode("robocup_strategy_gui_reload_client")
        _reload_client = _reload_client_node.create_client(
            _TriggerSrv, "/robocup_strategy/reload",
        )
        return True
    except Exception:
        _reload_client_node = None
        _reload_client = None
        return False


def _call_reload_service_best_effort() -> dict[str, Any]:
    """Called immediately after save. Never throws even if the service is unavailable or times out.

    Implementation note: _reload_client_node may not be added to the executor in main_web.py,
    so the future may not be spun automatically. To handle this, rclpy.spin_until_future_complete
    is called best-effort — briefly spinning the node to let the future complete.
    All steps are swallowed with try/except.
    """
    if not _ensure_reload_client():
        return {"ok": False, "detail": "rclpy unavailable or client creation failed (mtime polling is backup)"}
    try:
        if not _reload_client.wait_for_service(timeout_sec=0.2):
            return {
                "ok": False,
                "detail": "service /robocup_strategy/reload unavailable (commander not running?) — mtime polling is backup",
            }
        req = _TriggerSrv.Request()
        future = _reload_client.call_async(req)

        # R-5 future spin: main_web.py's executor may not be spinning this node,
        # so call spin_until_future_complete here on a best-effort basis.
        # Even if it fails, mtime polling will catch the update.
        try:
            rclpy.spin_until_future_complete(
                _reload_client_node, future, timeout_sec=0.5,
            )
        except Exception:
            # Even if spinning itself fails, swallow it and continue with polling fallback.
            pass

        # If spin_until_future_complete does not finish it, wait once more by polling.
        if not future.done():
            deadline = time.monotonic() + 0.3
            while not future.done() and time.monotonic() < deadline:
                time.sleep(0.01)

        if not future.done():
            return {"ok": False, "detail": "service 응답 timeout — mtime 폴링이 backup"}
        res = future.result()
        return {"ok": bool(res.success), "detail": res.message or ""}
    except Exception as e:
        return {"ok": False, "detail": f"service call 예외: {e!r} (mtime 폴링이 backup)"}


def create_app(yaml_path: Path, static_dir: Path, live_state: Any = None) -> FastAPI:
    app = FastAPI(title="RoboCup Strategy GUI")

    class _NoCacheMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            p = request.url.path
            # Disable caching not only for js/css but also for the root HTML (index.html).
            # Otherwise the browser may cache index.html and UI changes (for example new buttons)
            # will not appear until a hard refresh.
            if (p.startswith("/js/") or p.startswith("/css/")
                    or p == "/" or p.endswith(".html")):
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            return response

    app.add_middleware(_NoCacheMiddleware)

    # ─── API ──────────────────────────────────────────────────────────

    @app.get("/api/field_config")
    async def api_field_config() -> dict[str, Any]:
        return zone_store.get_field_config()

    @app.get("/api/zones")
    async def api_get_zones() -> dict[str, Any]:
        try:
            return zone_store.load_zones(yaml_path)
        except ValueError as e:
            raise HTTPException(status_code=500, detail=f"YAML 파싱 실패: {e}")

    @app.put("/api/zones")
    async def api_put_zones(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            normalized = zone_store.save_zones(yaml_path, payload)
        except ValueError as e:
            # Validation failures return 400.
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": str(e)},
            )
        except OSError as e:
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": f"파일 쓰기 실패: {e}"},
            )

        # R-5: call /robocup_strategy/reload immediately after save.
        # mtime polling reaches the same result within 100 ms, but the explicit trigger is
        # faster and easier to debug. Even if the service is unavailable, fail soft because
        # mtime polling remains as the backup.
        reload_status = _call_reload_service_best_effort()

        return {
            "ok": True,
            "saved_to": str(yaml_path),
            "zone_count": len(normalized["zones"]),
            "reload": reload_status,  # {"ok": bool, "detail": "..."}
        }

    @app.get("/api/zones/path")
    async def api_zones_path() -> dict[str, Any]:
        return {"path": str(yaml_path), "exists": yaml_path.exists()}

    @app.get("/api/live")
    async def api_live() -> dict[str, Any]:
        """Realtime robot/ball position snapshot polled by the frontend.

        If live_state is unavailable (for example ROS message import failure),
        return enabled=false gracefully. Never throw so the polling loop stays alive.
        """
        if live_state is None:
            return {"enabled": False, "robots": [], "ball": None}
        try:
            return live_state.snapshot()
        except Exception as e:  # noqa: BLE001 - prioritize polling stability
            return {"enabled": False, "robots": [], "ball": None, "error": repr(e)}

    # Static files (mount last so this becomes the catch-all).
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
