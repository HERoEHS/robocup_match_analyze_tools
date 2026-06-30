#include "robocup_msgs/robocup_ros_bridge.hpp"

using namespace std;

namespace robocup
{

  void PrintControlData(RoboCupGameControlData &control_data)
  {
    cout << "\n";
    cout << "------[ GameControlData ]--------------------------------\n";
    cout << "\n";
    cout << "                 header : " << string(control_data.header, 4) << "\n";
    cout << "                version : " << (int)control_data.version << "\n";
    cout << "          packet number : " << (int)control_data.packetNumber << "\n";
    cout << "       players per team : " << (int)control_data.playersPerTeam << "\n";
    cout << "       competition type : " << (int)control_data.competitionType << "\n";
    cout << "                stopped : " << (int)control_data.stopped << "\n";
    cout << "             game phase : " << (int)control_data.gamePhase << "\n";
    cout << "                  state : " << (int)control_data.state << "\n";
    cout << "               set play : " << (int)control_data.setPlay << "\n";
    cout << "             first half : " << (int)control_data.firstHalf << "\n";
    cout << "           kicking team : " << (int)control_data.kickingTeam << "\n";
    cout << "         secs remaining : " << (int)control_data.secsRemaining << "\n";
    cout << "         secondary time : " << (int)control_data.secondaryTime << "\n";
    cout << "\n";
    cout << "---------------------------------------------------------\n";
    cout << "\n";
  }

  void PrintTeamInfo(TeamInfo &team)
  {
    cout << "------[ Team Number " << (int)team.teamNumber << " ]--------------------------------------\n";
    cout << "  field player colour : " << (int)team.fieldPlayerColour << "\n";
    cout << "   goalkeeper colour  : " << (int)team.goalkeeperColour << "\n";
    cout << "           goalkeeper : " << (int)team.goalkeeper << "\n";
    cout << "                score : " << (int)team.score << "\n";
    cout << "         penalty shot : " << (int)team.penaltyShot << "\n";
    cout << "         single shots : " << (int)team.singleShots << "\n";
    cout << "       message budget : " << (int)team.messageBudget << "\n";
    cout << "\n";
    cout << "---------------------------------------------------------\n";
    cout << "\n";
  }

  void PrintRobotInfo(RobotInfo &player)
  {
    cout << "------[ Player Info ]------------------------------------\n";
    cout << "             penalty : " << (int)player.penalty << "\n";
    cout << " secsTillUnpenalised : " << (int)player.secsTillUnpenalised << "\n";
    cout << "            cautions : " << (int)player.cautions << "\n";
    cout << "\n";
    cout << "---------------------------------------------------------\n";
    cout << "\n";
  }

  // [DEPRECATED — v18 compat shim]
  // Synthesizes the legacy v18 secondary_state byte from v19's separate gamePhase + setPlay
  // fields. v19-native condition nodes (IsSetPlay / IsGamePhase / IsKickingTeam) no longer
  // read `secondary_state`, `secondary_state_info`, or `kick_off_team`. This synthesis is
  // retained for any out-of-tree consumer. Remove once those consumers migrate to the v19
  // native fields (data.set_play, data.game_phase, data.kicking_team, data.state).
  static uint8_t SynthesizeSecondaryState(const RoboCupGameControlData &src)
  {
    if (src.setPlay != SET_PLAY_NONE)
    {
      switch (src.setPlay)
      {
      case SET_PLAY_DIRECT_FREE_KICK:   return STATE2_DIRECT_FREEKICK;
      case SET_PLAY_INDIRECT_FREE_KICK: return STATE2_INDIRECT_FREEKICK;
      case SET_PLAY_PENALTY_KICK:       return STATE2_PENALTYKICK;
      case SET_PLAY_THROW_IN:           return STATE2_THROW_IN;
      case SET_PLAY_GOAL_KICK:          return STATE2_GOAL_KICK;
      case SET_PLAY_CORNER_KICK:        return STATE2_CORNER_KICK;
      default:                          return STATE2_NORMAL;
      }
    }
    else
    {
      switch (src.gamePhase)
      {
      case GAME_PHASE_NORMAL:            return STATE2_NORMAL;
      case GAME_PHASE_PENALTY_SHOOT_OUT: return STATE2_PENALTYSHOOT;
      case GAME_PHASE_EXTRA_TIME:        return STATE2_OVERTIME;
      case GAME_PHASE_TIMEOUT:           return STATE2_TIMEOUT;
      default:                           return STATE2_NORMAL;
      }
    }
  }

  void SetRoboCupGameControlRosData(robocup_msgs::msg::RoboCupGameControlRosData &data, const RoboCupGameControlData &src, const int team_index, const int robot_index)
  {
    data.team_index = team_index;
    data.robot_index = robot_index;

    SetRoboCupGameControlRosData(data, src);
  }

  void SetRoboCupGameControlRosData(robocup_msgs::msg::RoboCupGameControlRosData &data, const RoboCupGameControlData &src)
  {
    data.header = string(src.header, 4);
    data.version = src.version;
    data.packet_number = src.packetNumber;
    data.players_per_team = src.playersPerTeam;
    data.competition_type = src.competitionType;
    data.stopped = src.stopped;
    data.game_phase = src.gamePhase;
    data.state = src.state;
    data.set_play = src.setPlay;
    data.first_half = src.firstHalf;
    data.kicking_team = src.kickingTeam;
    data.secs_remaining = src.secsRemaining;
    data.secondary_time = src.secondaryTime;

    SetTeamRosInfo(data.teams[0], src.teams[0]);
    SetTeamRosInfo(data.teams[1], src.teams[1]);

    // [DEPRECATED — v18 compat] populate legacy fields for out-of-tree consumers only.
    data.secondary_state = SynthesizeSecondaryState(src);
    data.secondary_state_info[0] = src.kickingTeam;
    data.secondary_state_info[1] = src.state;
    data.secondary_state_info[2] = 0;
    data.secondary_state_info[3] = 0;
    data.kick_off_team = src.kickingTeam;
  }

  void SetTeamRosInfo(robocup_msgs::msg::TeamRosInfo &info, const TeamInfo &src)
  {
    info.team_number = src.teamNumber;
    info.field_player_colour = src.fieldPlayerColour;
    info.goalkeeper_colour = src.goalkeeperColour;
    info.goalkeeper = src.goalkeeper;
    info.score = src.score;
    info.penalty_shot = src.penaltyShot;
    info.single_shots = src.singleShots;
    info.message_budget = src.messageBudget;

    for (int i = 0; i < MAX_NUM_PLAYERS; i++)
    {
      SetRobotRosInfo(info.players[i], src.players[i]);
    }
  }

  void SetRobotRosInfo(robocup_msgs::msg::RobotRosInfo &info, const RobotInfo &src)
  {
    info.penalty = src.penalty;
    info.secs_till_unpenalised = src.secsTillUnpenalised;
    info.cautions = src.cautions;
  }

  void SetRoboCupGameControlData(RoboCupGameControlData &data, const robocup_msgs::msg::RoboCupGameControlRosData &src)
  {
    size_t len = std::min<size_t>(4, src.header.size());
    std::copy_n(src.header.c_str(), len, data.header);
    if (len < 4) data.header[len] = '\0';

    data.version = src.version;
    data.packetNumber = src.packet_number;
    data.playersPerTeam = src.players_per_team;
    data.competitionType = src.competition_type;
    data.stopped = src.stopped;
    data.gamePhase = src.game_phase;
    data.state = src.state;
    data.setPlay = src.set_play;
    data.firstHalf = src.first_half;
    data.kickingTeam = src.kicking_team;
    data.secsRemaining = src.secs_remaining;
    data.secondaryTime = src.secondary_time;

    SetTeamInfo(data.teams[0], src.teams[0]);
    SetTeamInfo(data.teams[1], src.teams[1]);
  }

  void SetTeamInfo(TeamInfo &info, const robocup_msgs::msg::TeamRosInfo &src)
  {
    info.teamNumber = src.team_number;
    info.fieldPlayerColour = src.field_player_colour;
    info.goalkeeperColour = src.goalkeeper_colour;
    info.goalkeeper = src.goalkeeper;
    info.score = src.score;
    info.penaltyShot = src.penalty_shot;
    info.singleShots = src.single_shots;
    info.messageBudget = src.message_budget;

    for (int i = 0; i < MAX_NUM_PLAYERS; i++)
    {
      SetRobotInfo(info.players[i], src.players[i]);
    }
  }

  void SetRobotInfo(RobotInfo &info, const robocup_msgs::msg::RobotRosInfo &src)
  {
    info.penalty = src.penalty;
    info.secsTillUnpenalised = src.secs_till_unpenalised;
    info.cautions = src.cautions;
  }

  void SetRoboCupGameControlRosReturnData(robocup_msgs::msg::RoboCupGameControlRosReturnData &data, const RoboCupGameControlReturnData &src)
  {
    data.header = string(src.header, 4);
    data.version = src.version;
    data.player_num = src.playerNum;
    data.team_num = src.teamNum;
    data.fallen = src.fallen;
    for (int i = 0; i < 3; i++) data.pose[i] = src.pose[i];
    data.ball_age = src.ballAge;
    for (int i = 0; i < 2; i++) data.ball[i] = src.ball[i];
  }

  void SetRoboCupGameControlReturnData(RoboCupGameControlReturnData &data, const robocup_msgs::msg::RoboCupGameControlRosReturnData &src)
  {
    size_t len = std::min<size_t>(4, src.header.size());
    std::copy_n(src.header.c_str(), len, data.header);
    if (len < 4) data.header[len] = '\0';

    data.version = src.version;
    data.playerNum = src.player_num;
    data.teamNum = src.team_num;
    data.fallen = src.fallen;
    for (int i = 0; i < 3; i++) data.pose[i] = src.pose[i];
    data.ballAge = src.ball_age;
    for (int i = 0; i < 2; i++) data.ball[i] = src.ball[i];
  }

} // namespace robocup
