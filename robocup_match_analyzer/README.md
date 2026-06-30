# robocup_match_analyzer

A browser-based post-match analysis tool for RoboCup MCAP recordings. Load one or more `.mcap` files and replay the match on an interactive 2D field with heatmaps, Voronoi diagrams, event bookmarks, and per-robot statistics.

![Match analyzer UI](docs/images/match_analyzer.png)

> *Screenshot: interactive field replay with robot trails and Voronoi overlay. Add a screenshot here after launching the tool.*

---

## Features

- **Multi-robot replay** — load recordings from all robots at once; timelines are aligned by GameController `READY` state
- **Field visualization** — robot positions, headings, destinations, ball, opponents, and vision detections
- **Heatmap** — robot activity, ball movement, or kick locations over configurable time ranges
- **Voronoi / space control** — per-team spatial dominance updated every frame
- **Event bookmarks** — automatically marks `READY/SET/PLAYING`, goals, falls, and kicks on the timeline
- **Segment analysis** — select any time window (or auto-generated segment) to get team and per-robot statistics (distance, kicks, falls, max speed)
- **Ball possession** — fused possession timeline with turnover counts and zone distribution
- **Merged download** — export all loaded bags as a single time-sorted MCAP zip
- **English / Korean UI toggle**

---

## Quick Start

### Build

```bash
cd <workspace>
colcon build --packages-select robocup_match_analyzer
source install/setup.bash
```

### Launch

```bash
ros2 launch robocup_match_analyzer analyzer.launch.py
```

Open `http://localhost:8096` in a browser.

To specify a data directory directly:

```bash
ros2 launch robocup_match_analyzer analyzer.launch.py \
  data_dir:=~/blackbox_data \
  web_port:=8096
```

---

## Usage

1. Enter the path to your MCAP directory in the top input field and click **Apply**.
2. Click **Select Files** and check the `.mcap` sessions to load.
3. Click **Load** — robots appear on the field once loading is complete.
4. Use the timeline slider, playback speed, and step buttons to navigate.
5. Click **Merged Download** to export all loaded sessions as one MCAP zip.

---

## File Naming and Robot ID Detection

The file browser detects robot IDs from the file name:

```
robot1_20260622_231803.mcap      → robot 1
robocup_1_20260622_231803.mcap   → robot 1
```

Files that do not match either pattern show `?` as the robot ID, but loading still works via internal MCAP topic names.

---

## Supported Topics (after robot prefix is stripped)

| Topic key | Used for |
|-----------|----------|
| `robocup/localization/pose` | Robot position, heatmap, trail |
| `robocup/destination` | Destination marker and connecting line |
| `robocup/current_bt_node` | Robot card, kick event detection |
| `robocup/lifted` | Fall event |
| `robocup/detected_objects` | Vision layer (ball, ally, robot) |
| `robocup/udp/data` | UDP teammate positions, pose fallback |
| `robocup/cooperative_perception/enemies` | Opponent markers, space control |
| `robocup/game_control_data` | Score, state, time alignment |

---

## Time Alignment

When multiple `.mcap` files are loaded together:
- The first `READY` state in any file anchors `t = 0`.
- Files without `READY` are aligned using GameController clock fields.
- Files with no GameController data at all are aligned by earliest raw timestamp.

---

## Architecture

```
Browser  ──GET /api/frame──►  web_server.py (FastAPI, port 8096)
                                    │
                               mcap_loader.py
                                    │  (reads .mcap via rosbag2_py)
                               per-robot data arrays
                                    │
                              frame_at(t) → JSON → browser renders field
```

---

## Dependencies

```bash
pip install fastapi uvicorn
sudo apt install ros-${ROS_DISTRO}-rosbag2-storage-mcap
```

- `rclpy`, `rosbag2_py`, `rosidl_runtime_py`
- `robocup_msgs` (in this repo)
