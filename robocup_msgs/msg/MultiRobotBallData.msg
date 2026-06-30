std_msgs/Header header
uint8 my_player_id
robocup_msgs/NamedPose[] entries

# Number of observations contributing to CI fusion (fusion confidence).
# 0 when entries is empty (no ball).
uint8 fused_num_sources
