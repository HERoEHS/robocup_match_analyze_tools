string header
uint8 version
uint8 packet_number
uint8 players_per_team
uint8 competition_type
uint8 stopped
uint8 game_phase
uint8 state
uint8 set_play
uint8 first_half
uint8 kicking_team
int16 secs_remaining
int16 secondary_time
robocup_msgs/TeamRosInfo[2] teams

# Backward compatibility (synthesized in bridge from game_phase + set_play)
uint8 secondary_state
uint8[4] secondary_state_info
uint8 kick_off_team

uint8 team_index
uint8 robot_index
