"""Entry point for robocup_match_analyzer web GUI."""
from __future__ import annotations

import argparse
import os
import signal
from pathlib import Path

import rclpy
import uvicorn

from robocup_match_analyzer.web_server import create_app


def _resolve_static_dir() -> Path:
    here = Path(os.path.dirname(os.path.abspath(__file__))).resolve()

    for parent in here.parents:
        share_static = parent / 'share' / 'robocup_match_analyzer' / 'static'
        if (share_static / 'index.html').exists():
            return share_static

    src = here / 'static'
    if (src / 'index.html').exists():
        return src

    try:
        from ament_index_python.packages import get_package_share_directory

        share_static = Path(get_package_share_directory('robocup_match_analyzer')) / 'static'
        if (share_static / 'index.html').exists():
            return share_static
    except Exception:
        pass

    raise FileNotFoundError('robocup_match_analyzer static directory not found')


def main(args=None) -> None:
    parser = argparse.ArgumentParser(description='RoboCup Match Analyzer GUI')
    parser.add_argument('--web-port', type=int, default=8096)
    parser.add_argument('--data-dir', type=str,
                        default=str(Path('~/blackbox_data/strategy_gui_sim_split').expanduser()))
    parser.add_argument('--our-team-number', type=int, default=0,
                        help='Our team number (0 = select in UI)')
    ns, _unknown = parser.parse_known_args(args=args)

    data_dir = Path(ns.data_dir).expanduser()
    static_dir = _resolve_static_dir()
    web_port = ns.web_port

    # Initialize rclpy — required for deserialize_message
    rclpy.init(args=None)

    app = create_app(data_dir=data_dir, static_dir=static_dir, our_team_number=ns.our_team_number)

    print(f'[robocup_match_analyzer] Data directory: {data_dir}', flush=True)
    print(f'[robocup_match_analyzer] Browser access: http://localhost:{web_port}', flush=True)

    def _shutdown(signum=None, frame=None):
        try:
            rclpy.shutdown()
        except Exception:
            pass
        os._exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    config = uvicorn.Config(app, host='0.0.0.0', port=web_port, log_level='warning')
    server = uvicorn.Server(config)
    try:
        server.run()
    except KeyboardInterrupt:
        _shutdown()


if __name__ == '__main__':
    main()
