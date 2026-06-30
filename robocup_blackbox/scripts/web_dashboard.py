#!/usr/bin/env python3
"""AEI Robotics Blackbox Health Web Dashboard.

Serves a simple HTML dashboard that subscribes to /blackbox/health and
displays recording status, topic counts, and errors.

Usage:
    ./web_dashboard.py [--port 8766]
"""

import argparse
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

health_data = {
    "connected": False,
    "robot_name": "Unknown",
    "recording_status": "stopped",
    "current_file": "N/A",
    "duration": "N/A",
    "topics": {},
    "errors": [],
    "last_update": None,
    "last_update_ts": None,  # epoch seconds of last /blackbox/health msg (for staleness)
}
health_lock = threading.Lock()

# If no /blackbox/health arrives within this many seconds, treat the writer node
# as gone and stop showing the (now stale) last-known snapshot as live.
STALE_TIMEOUT_SEC = 5.0

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="2">
    <title>Blackbox Health Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            color: #00d4ff;
            margin-bottom: 30px;
            font-size: 2rem;
            text-shadow: 0 0 10px rgba(0, 212, 255, 0.3);
        }
        .waiting {
            text-align: center;
            font-size: 1.2rem;
            color: #ff9800;
            margin-top: 50px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
        }
        .card h2 {
            color: #00d4ff;
            font-size: 1.1rem;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(0, 212, 255, 0.3);
        }
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        .info-row:last-child { border-bottom: none; }
        .label { color: #888; }
        .value { font-weight: 600; color: #fff; }
        .status-recording { color: #4caf50; }
        .status-stopped { color: #f44336; }
        .status-ok { color: #4caf50; }
        .status-warn { color: #ff9800; }
        .status-error { color: #f44336; }
        .topic-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        .topic-table th, .topic-table td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        .topic-table th {
            color: #00d4ff;
            font-weight: 600;
            background: rgba(0, 212, 255, 0.1);
        }
        .topic-table tr:hover {
            background: rgba(255, 255, 255, 0.03);
        }
        .error-box {
            background: rgba(244, 67, 54, 0.1);
            border: 1px solid rgba(244, 67, 54, 0.3);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
        }
        .error-box .error-name {
            color: #f44336;
            font-weight: 600;
            margin-bottom: 5px;
        }
        .error-box .error-msg {
            color: #ff8a80;
            font-size: 0.9rem;
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            color: #666;
            font-size: 0.85rem;
        }
        .timestamp {
            color: #888;
            font-size: 0.85rem;
            text-align: center;
            margin-top: 10px;
        }
        @media (max-width: 600px) {
            body { padding: 10px; }
            h1 { font-size: 1.5rem; }
            .grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Blackbox Health Dashboard</h1>
        {content}
        <div class="timestamp">Last updated: {timestamp}</div>
        <div class="footer">Auto-refreshes every 2 seconds</div>
    </div>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_response(404)
            self.end_headers()
            return

        with health_lock:
            data = dict(health_data)

        ts = data["last_update_ts"]
        stale = ts is None or (time.time() - ts) > STALE_TIMEOUT_SEC

        if not data["connected"]:
            content = '<div class="waiting">Waiting for /blackbox/health...<br><span style="font-size:0.9rem;color:#888;">Ensure blackbox_writer_node is running and publishing diagnostics.</span></div>'
        elif stale:
            age = "?" if ts is None else f"{time.time() - ts:.0f}s"
            content = (
                f'<div class="waiting">Connection lost &mdash; no /blackbox/health for {age}.<br>'
                '<span style="font-size:0.9rem;color:#888;">blackbox_writer_node likely stopped. '
                f'Last known snapshot below (stale).</span></div>'
                + self._render_dashboard(data)
            )
        else:
            content = self._render_dashboard(data)

        timestamp = data["last_update"] or "Never"
        html = HTML_TEMPLATE.replace("{content}", content).replace("{timestamp}", timestamp)

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass

    def _render_dashboard(self, data):
        recording_class = {
            "recording": "status-recording",
            "idle": "status-warn",
        }.get(data["recording_status"], "status-stopped")

        status_card = f"""
        <div class="card">
            <h2>Status</h2>
            <div class="info-row">
                <span class="label">Robot</span>
                <span class="value">{data["robot_name"]}</span>
            </div>
            <div class="info-row">
                <span class="label">Recording</span>
                <span class="value {recording_class}">{data["recording_status"].upper()}</span>
            </div>
            <div class="info-row">
                <span class="label">Current File</span>
                <span class="value">{data["current_file"]}</span>
            </div>
            <div class="info-row">
                <span class="label">Duration</span>
                <span class="value">{data["duration"]}</span>
            </div>
        </div>
        """

        topics_card = '<div class="card"><h2>Topics</h2>'
        if data["topics"]:
            topics_card += """
            <table class="topic-table">
                <thead>
                    <tr><th>Topic</th><th>Queue Size</th><th>Status</th></tr>
                </thead>
                <tbody>
            """
            for topic, info in sorted(data["topics"].items()):
                level_class = "status-ok" if info["level"] == "OK" else ("status-warn" if info["level"] == "WARN" else "status-error")
                topics_card += f"""
                    <tr>
                        <td>{topic}</td>
                        <td>{info.get("queue_size", "N/A")}</td>
                        <td class="{level_class}">{info["level"]}</td>
                    </tr>
                """
            topics_card += "</tbody></table>"
        else:
            topics_card += '<p style="color:#888;">No topic data available.</p>'
        topics_card += "</div>"

        errors_section = ""
        if data["errors"]:
            errors_section = '<div class="card"><h2>Errors</h2>'
            for err in data["errors"]:
                errors_section += f"""
                <div class="error-box">
                    <div class="error-name">{err["name"]}</div>
                    <div class="error-msg">{err["message"]}</div>
                </div>
                """
            errors_section += "</div>"

        return f"""
        <div class="grid">
            {status_card}
            {topics_card}
        </div>
        {errors_section}
        """


class DashboardNode(Node):
    def __init__(self):
        super().__init__("web_dashboard")

        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)
        self.sub = self.create_subscription(
            DiagnosticArray,
            "/blackbox/health",
            self.on_health,
            qos,
        )

        self.get_logger().info("Subscribed to /blackbox/health")

    def on_health(self, msg):
        global health_data

        robot_name = "Unknown"
        recording_status = "stopped"
        current_file = "N/A"
        duration = "N/A"
        topics = {}
        errors = []

        for status in msg.status:
            if status.hardware_id:
                robot_name = status.hardware_id

            if status.name == "mcap_writer":
                if status.level != DiagnosticStatus.OK:
                    recording_status = "stopped"
                else:
                    # Writer is open; the "recording" KeyValue tells us whether data
                    # is actually being written ("recording") or it is idle.
                    recording_status = "recording"
                    for kv in status.values:
                        if kv.key == "recording":
                            recording_status = "recording" if kv.value == "true" else "idle"

                for kv in status.values:
                    if kv.key == "file_size":
                        try:
                            size_bytes = int(kv.value)
                            current_file = self._human_size(size_bytes)
                        except ValueError:
                            current_file = kv.value

            elif status.name.startswith("throttle_"):
                topic_name = status.name.replace("throttle_", "")
                level_str = self._level_to_str(status.level)
                topic_info = {
                    "level": level_str,
                    "message": status.message,
                }
                for kv in status.values:
                    if kv.key == "queue_size":
                        topic_info["queue_size"] = kv.value
                topics[topic_name] = topic_info

                if status.level == DiagnosticStatus.ERROR:
                    errors.append({
                        "name": status.name,
                        "message": status.message,
                    })

            if status.level == DiagnosticStatus.ERROR and not status.name.startswith("throttle_"):
                errors.append({
                    "name": status.name,
                    "message": status.message,
                })

        with health_lock:
            health_data.update({
                "connected": True,
                "robot_name": robot_name,
                "recording_status": recording_status,
                "current_file": current_file,
                "duration": duration,
                "topics": topics,
                "errors": errors,
                "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_update_ts": time.time(),
            })

    @staticmethod
    def _level_to_str(level):
        if level == DiagnosticStatus.OK:
            return "OK"
        elif level == DiagnosticStatus.WARN:
            return "WARN"
        elif level == DiagnosticStatus.ERROR:
            return "ERROR"
        return "UNKNOWN"

    @staticmethod
    def _human_size(size_bytes):
        units = ["B", "KB", "MB", "GB", "TB"]
        power = 1024
        idx = 0
        size = float(size_bytes)
        while size >= power and idx < len(units) - 1:
            size /= power
            idx += 1
        return f"{size:.2f} {units[idx]}"


def main():
    parser = argparse.ArgumentParser(description="Blackbox Health Web Dashboard")
    parser.add_argument("--port", type=int, default=8766, help="HTTP server port")
    args = parser.parse_args()

    rclpy.init()
    node = DashboardNode()

    try:
        server = HTTPServer(("", args.port), DashboardHandler)
    except OSError as e:
        node.get_logger().error(f"Port {args.port} unavailable: {e}")
        rclpy.shutdown()
        return 1
    port = args.port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    node.get_logger().info(f"Dashboard available at http://localhost:{port}")

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except ExternalShutdownException:
        pass
    finally:
        server.shutdown()
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    exit(main())
