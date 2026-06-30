from __future__ import annotations

import atexit
import ctypes
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import rclpy
import uvicorn
from ament_index_python.packages import get_package_share_directory
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node

from robocup_realtime_monitoring import zone_store
from robocup_realtime_monitoring.live_state import LiveState
from robocup_realtime_monitoring.udp_listener import TEAM_MESSAGE_PORT_BASE, UdpTeamListener
from robocup_realtime_monitoring.web_server import create_app


def _kill_existing_on_port(port: int) -> None:
    try:
        result = subprocess.run(
            ["lsof", "-t", f"-i:{port}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            for pid in result.stdout.strip().split():
                try:
                    os.kill(int(pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
    except FileNotFoundError:
        pass
    except Exception:
        pass


def _enable_pdeathsig() -> None:
    try:
        libc = ctypes.CDLL("libc.so.6")
        PR_SET_PDEATHSIG = 1
        libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    except Exception:
        pass


def _resolve_static_dir() -> Path:
    """Prefer source path (hot-reload during development); fall back to share/."""
    share_static = Path(get_package_share_directory("robocup_realtime_monitoring")) / "static" / "strategy"
    src_static = Path(os.path.dirname(os.path.abspath(__file__))) / "static" / "strategy"
    if (src_static / "index.html").exists():
        return src_static
    return share_static


def main(args=None) -> None:
    _enable_pdeathsig()
    rclpy.init(args=args)

    node = Node("robocup_strategy_gui")
    node.declare_parameter("web_port", 8094)
    node.declare_parameter("zones_path", "")
    # Real-time position overlay parameters (based on UDP team communication MessageV2).
    #   team_number: 0 → uses default value 25.
    #     UDP port = TEAM_MESSAGE_PORT_BASE(10000) + team_number (must match sender).
    #   udp_port: if >0, overrides the auto-calculated port and uses this port directly (debug/special network).
    #   udp_bind_addr: usually 0.0.0.0 (broadcast receive). Shared with receiver via SO_REUSEPORT.
    #   live_stale_sec: hide robot/ball if no packet received for this duration.
    #   skip_zero_pose: hide packets where position is exactly (0,0,0) (localization not initialized).
    node.declare_parameter("team_number", 0)
    node.declare_parameter("udp_port", 0)
    node.declare_parameter("udp_bind_addr", "0.0.0.0")
    node.declare_parameter("live_stale_sec", 2.0)
    node.declare_parameter("skip_zero_pose", True)
    #   ball_requires_detected: if True, show the ball only when ball_detected=True (hide when not detected).
    #     Default True — policy: "if the ball is not seen (not detected), it should disappear from the screen."
    #     (If False, the ball is shown as long as ball_position is valid → stays visible at last position even when not detected.
    #      In environments without a detected_ball publisher, set to False to make the ball visible.)
    node.declare_parameter("ball_requires_detected", True)

    web_port: int = node.get_parameter("web_port").get_parameter_value().integer_value
    zones_override: str = (
        node.get_parameter("zones_path").get_parameter_value().string_value
    )
    team_number = int(
        node.get_parameter("team_number").get_parameter_value().integer_value)
    if team_number <= 0:
        team_number = 25
    udp_port = int(
        node.get_parameter("udp_port").get_parameter_value().integer_value)
    if udp_port <= 0 or udp_port > 65535:
        udp_port = TEAM_MESSAGE_PORT_BASE + team_number
    udp_bind_addr: str = (
        node.get_parameter("udp_bind_addr").get_parameter_value().string_value
    ) or "0.0.0.0"
    live_stale_sec = (
        node.get_parameter("live_stale_sec").get_parameter_value().double_value
    )
    if live_stale_sec <= 0:  # 0/negative → safe default (prevent all data from going stale immediately)
        live_stale_sec = 2.0
    skip_zero_pose = bool(
        node.get_parameter("skip_zero_pose").get_parameter_value().bool_value)
    ball_requires_detected = bool(
        node.get_parameter("ball_requires_detected").get_parameter_value().bool_value)

    yaml_path = zone_store.resolve_yaml_path(zones_override or None)
    static_dir = _resolve_static_dir()

    node.get_logger().info(f"Strategy YAML: {yaml_path}")
    node.get_logger().info(f"Static files: {static_dir}")

    _kill_existing_on_port(web_port)

    # Real-time position state store + UDP team communication receiver (fail-soft).
    live_state = LiveState(
        stale_sec=live_stale_sec,
        skip_zero_pose=skip_zero_pose,
        ball_requires_detected=ball_requires_detected,
    )
    udp_listener = UdpTeamListener(
        live_state, port=udp_port, bind_addr=udp_bind_addr, logger=node.get_logger(),
    )
    udp_listener.start()
    node.get_logger().info(
        f"Real-time position overlay (UDP): team={team_number} port={udp_port} "
        f"stale={live_stale_sec}s skip_zero={skip_zero_pose} "
        f"ball_requires_detected={ball_requires_detected}",
    )

    app = create_app(yaml_path=yaml_path, static_dir=static_dir, live_state=live_state)

    executor = SingleThreadedExecutor()
    executor.add_node(node)
    spin_thread = threading.Thread(
        target=executor.spin, daemon=True, name="ros2-executor",
    )
    spin_thread.start()

    _shutdown_once = threading.Event()
    _server: uvicorn.Server | None = None

    def _shutdown(force: bool = False) -> None:
        if _shutdown_once.is_set() and not force:
            return
        _shutdown_once.set()
        node.get_logger().info("Shutdown sequence started")
        try:
            udp_listener.stop()
        except Exception:
            pass
        if _server is not None:
            _server.should_exit = True
        try:
            executor.shutdown(timeout_sec=3.0)
            node.destroy_node()
            rclpy.shutdown()
        except Exception:
            pass
        node.get_logger().info("Shutdown complete")
        os._exit(0)

    atexit.register(lambda: _shutdown(force=True))

    def _signal_handler(signum, frame):
        _shutdown()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGHUP, _signal_handler)

    # Access info — enumerate local + wired/wireless IPs (same pattern as robocup_gui)
    try:
        import socket
        import struct
        import fcntl
        ips = []
        for iface in sorted(os.listdir('/sys/class/net/')):
            if iface == 'lo':
                continue
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                ip = socket.inet_ntoa(fcntl.ioctl(
                    s.fileno(), 0x8915, struct.pack('256s', iface[:15].encode())
                )[20:24])
                s.close()
                if not ip.startswith('127.') and not ip.startswith('172.') and not ip.startswith('100.'):
                    ips.append((ip, iface))
            except IOError:
                pass
        if not ips:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ips.append((s.getsockname()[0], "default"))
                s.close()
            except Exception:
                pass
        node.get_logger().info(
            f"Browser access: http://localhost:{web_port} (local)"
        )
        for ip, iface in ips:
            if iface.startswith('wl') or iface.startswith('wlan'):
                link_type = 'wireless'
            elif iface.startswith('en') or iface.startswith('eth'):
                link_type = 'wired'
            else:
                link_type = iface
            node.get_logger().info(
                f"Browser access: http://{ip}:{web_port} ({link_type})"
            )
    except Exception:
        node.get_logger().info(
            f"Browser access: http://localhost:{web_port}"
        )

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=web_port,
        log_level="warning",
    )
    try:
        _server = uvicorn.Server(config)
        _server.run()
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()
