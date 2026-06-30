#pragma once
#include <string>
#include <vector>

struct TopicRule {
  std::string topic;           // e.g. "/tf"
  std::string output_topic;    // mcap channel name (usually same as topic)
  double hz = 0.0;             // target Hz, 0 means pass-through (no throttle)
  size_t queue_size = 1000;    // max buffer size before dropping old msgs
  bool write_all_buffered = false;  // if true, write every buffered msg in order when gate opens
};

struct TopicConfig {
  std::string robot_id;                    // e.g. "robot_1"
  std::string output_dir;                  // e.g. "~/.ros/bb"
  std::vector<TopicRule> topics;         // list of topics to record
  bool enable_live_stream = false;       // if true, also ROS-publish throttled msgs
  double timer_period_ms = 10.0;         // wall-timer period for checking queues
};

// Load config from YAML file
TopicConfig loadTopicConfig(const std::string& config_path);

// Resolve "~" to home directory
std::string resolveHomePath(const std::string& path);
