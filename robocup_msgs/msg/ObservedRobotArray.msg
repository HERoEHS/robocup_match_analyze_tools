# Shared teammate observations: global positions of teammates seen by one
# observer robot at the same moment.
#
# Usage:
#   Publish path: the cooperative_localization node converts its own vision
#                 observations to global coordinates and publishes them
#                 (cooperative_loc/observed_robots) -> UDP sender
#                 packs them into the wire slot.
#   Receive path: the UDP receiver reconstructs the observation slot from
#                 teammate packets and publishes it
#                 (udp/observed_robot) -> consumed by the
#                 cooperative_localization node.
#
# Contract:
#   - observer_id: observer (= original transmitting robot) player_id.
#     0 = invalid. Receivers can use this to store observations per observer
#     and avoid single-latch contention.
#   - observations[i].player_id: always 0 because the observed teammate cannot
#     be identified reliably from vision alone.
#   - observations[i].covariance: in the 6x6 row-major matrix, only
#     [0]=sigma^2_x, [7]=sigma^2_y, and [35]=sigma^2_yaw are valid because
#     the UDP wire format carries only the 3 diagonal terms.
#   - Recommended max array length is 2 (three-robot team: at most two
#     teammates besides self). Receivers should ignore extra entries.
std_msgs/Header header
uint8 observer_id
robocup_msgs/ProtoBufRobotData[] observations

# 1:1 parallel array with observations[i] representing fusion confidence.
#   - Filled only for the observer_id==0 (fusion result) path. Each value is
#     the number of distinct observing robots that contributed to the
#     corresponding cluster (cooperative_perception_fusion c.srcs.size()).
#   - For teammate observation paths (observer_id>0), leave it empty
#     (length 0 = not provided) for backward compatibility.
#   - Consumers should match by index only when
#     length==observations.length; otherwise treat it as 0.
uint8[] observation_num_sources
