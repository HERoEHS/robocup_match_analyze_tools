# robocup_match_analyzer

Browser-based post-match analysis tool for RoboCup MCAP recordings.
It loads selected `.mcap` files from a data directory, synchronizes them into one
match timeline, and replays the result on an interactive 2D field.

## Features

- Multi-file match loading from one directory view
- Interactive field replay with robots, ball, opponents, detections, and trails
- Heatmap modes for robot activity, ball movement, and kick locations
- Voronoi-based space control overlay and sampled trend analysis
- Event bookmarks for state, setplay, goal, fall, and kick events
- Segment analysis for state spans, setplay spans, goal windows, fall windows, and custom Start/End ranges
- Ball possession summary, possession timeline, and turnover statistics
- Team formation summary with centroid / width / depth / compactness metrics
- Merged download of the currently loaded file set
- PNG export of the current field view
- Korean / English UI toggle

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

To override the default path or port:

```bash
ros2 launch robocup_match_analyzer analyzer.launch.py \
  data_dir:=~/blackbox_data \
  web_port:=8096 \
  our_team_number:=0
```

Launch arguments:

- `data_dir`: root directory scanned by the file browser
- `web_port`: FastAPI / browser port
- `our_team_number`: team number used to identify our side in the scoreboard and goal-related labels (`0` = choose in UI)

## Usage

1. Launch the node and open the browser page.
2. Enter a directory path in the top bar and click `적용` / `Apply`.
3. If needed, click `목록 새로고침` / `Refresh` to rescan the directory.
4. Open `파일 선택` / `Select files`, then check the `.mcap` files you want to analyze.
5. Click `불러오기` / `Load`.
6. If two team numbers are present, select `우리팀` / `Our Team` in the header so the scoreboard order and goal-related labels use the correct side.
7. Use the timeline, play/pause button, seek-step selector, and speed selector to inspect the match.
8. Optionally use `병합 다운로드` / `Download merged` or `PNG 저장` / `Save PNG`.

Keyboard shortcuts:

- `Space`: play / pause
- `ArrowLeft`, `ArrowRight`: seek by the currently selected step size

## File Browser Behavior

The file browser does not recursively scan the whole disk.

- It scans `data_dir` itself and its immediate subdirectories only.
- It shows only paths matching `*.mcap`.
- Groups are sorted by newest file modification time first.
- The currently loaded session is built from the explicitly checked file list.

This means rollover artifacts such as `.mcap.1`, `.mcap.2`, or deeper nested bags are not shown unless they appear as direct `*.mcap` entries in the scanned scope.

## File Naming and Robot ID Detection

Robot IDs in the file browser are inferred from the filename when possible:

```text
robot1_20260622_231803.mcap      -> robot 1
robocup_1_20260622_231803.mcap   -> robot 1
```

If a filename does not match those patterns, the browser shows `?`.
Loading still works because the analyzer ultimately uses topic contents, not just the filename.

## Supported Topics

Topic matching happens after the per-robot prefix is stripped.
Both `robocup/...` and bare topic keys are supported by the loader.

| Topic key | Used for |
|-----------|----------|
| `robocup/localization/pose` | Robot position, replay, heatmap, trail |
| `robocup/destination` | Destination marker and line |
| `robocup/current_bt_node` | Robot state text, kick event detection |
| `robocup/lifted` | Fall detection |
| `robocup/detected_objects` | Per-robot vision ball / object overlay |
| `robocup/udp/data` | Teammate pose fallback and UDP overlays |
| `robocup/cooperative_perception/enemies` | Opponent markers and space control |
| `robocup/game_control_data` | Match state, score, setplay, time alignment |
| `robocup/rl_vel_cmd` | Velocity-command arrow overlay |

## Time Alignment

When multiple `.mcap` files are loaded together:

- Files with a first-half `READY` keep that `READY` as `t = 0`.
- Files without a usable `READY` are aligned by matching GameController progress fields against the READY-anchored reference timeline.
- If GC matching is unavailable but another file has a first-half `READY`, the loader falls back to that first-half wall-clock anchor.
- If no file provides a usable `READY` anchor at all, the loader falls back to the earliest raw timestamp.

Because of this, mid-match restart files can still be placed onto one shared match timeline instead of always jumping back to the start.

## Main Analysis Outputs

- Replay field with robot / enemy / ball overlays
- Heatmap with `progressive`, `all`, `first half`, `second half`, and `selected segment` ranges
- Timeline markers plus bookmark chips
- Match summary for full game / first half / second half
- Segment summary for the selected range
- Space control and team-formation charts
- Possession summary and live possession chip

## Architecture

```text
Browser
  ├─ GET  /api/sessions
  ├─ POST /api/load
  ├─ GET  /api/frame
  ├─ GET  /api/heatmap_preload
  ├─ GET  /api/space_control_samples
  ├─ GET  /api/possession_preload
  └─ GET  /api/download_merged

web_server.py
  ├─ file discovery / session registry
  ├─ FastAPI endpoints
  └─ merged-download creation

mcap_loader.py
  ├─ rosbag2_py MCAP loading
  ├─ cross-file time alignment
  ├─ frame extraction
  └─ bookmark / segment / summary generation
```

## Dependencies

Required ROS / Python pieces:

```bash
pip install fastapi uvicorn
sudo apt install ros-${ROS_DISTRO}-rosbag2-storage-mcap
```

Package/runtime dependencies used by this analyzer include:

- `rclpy`
- `rosbag2_py`
- `rosidl_runtime_py`
- `robocup_msgs`
- `geometry_msgs`
- `std_msgs`
