# robocup_msgs

A ROS 2 package that defines custom message types shared across all packages in this repository. It contains only `.msg` definitions — no nodes or launch files.

## Messages

| File | Description |
|------|-------------|
| `FoundObject.msg` | Single detected object (name, id, 3D position, ROI, velocity, score) |
| `FoundObjectArray.msg` | Array of `FoundObject` with a header |
| `FoundMatched.msg` | Detected object with match confirmation |
| `FoundMatchedArray.msg` | Array of `FoundMatched` |
| `ObservedRobotArray.msg` | Teammate/opponent observations reported by one robot |
| `ProtoBufRobotData.msg` | Compact robot pose for UDP transmission |
| `ProtoBufBallData.msg` | Compact ball data for UDP transmission |
| `RoboCupRobotData.msg` | Full robot state packet (pose, ball, others, GameController data, penalties) |
| `RoboCupGameControlRosData.msg` | GameController packet fields (state, teams, time, set play) |
| `RoboCupGameControlRosReturnData.msg` | Robot-to-GameController return message |
| `GlobalBallWithCovariance.msg` | Global ball position with uncertainty covariance |
| `MultiRobotBallData.msg` | Fused ball estimate from multiple robots |
| `MoveCommand.msg` | Navigation velocity command |
| `NamedPose.msg` | `Pose2D` with a string label |
| `RobotRosInfo.msg` | Per-robot status (penalties, score) |
| `TeamRosInfo.msg` | Per-team status (score, penalty info) |

## Build

Build this package before any other package in the repository, as they all depend on it.

```bash
cd <workspace>
colcon build --packages-select robocup_msgs
source install/setup.bash
```

## Notes

- This is a C++ `ament_cmake` package.
- It provides no nodes or launch files — message definitions only.
- All other packages in this repository list `robocup_msgs` as a dependency.
