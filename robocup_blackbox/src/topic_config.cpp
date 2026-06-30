#include <yaml-cpp/yaml.h>
#include <cstdlib>
#include "robocup_blackbox/topic_config.hpp"

namespace {
  std::string getEnvVar(const char* name) {
    const char* val = std::getenv(name);
    return val ? std::string(val) : "";
  }
}  // namespace

std::string resolveHomePath(const std::string& path) {
  if (path.empty()) return path;
  if (path[0] == '~') {
    std::string home = getEnvVar("HOME");
    if (home.empty()) {
      return path;
    }
    return home + (path.size() > 1 ? path.substr(1) : "");
  }
  return path;
}

TopicConfig loadTopicConfig(const std::string& config_path) {
  YAML::Node config = YAML::LoadFile(config_path);
  TopicConfig tc;

  if (config["robot_id"]) {
    tc.robot_id = config["robot_id"].as<std::string>();
  }
  if (config["output_dir"]) {
    tc.output_dir = resolveHomePath(config["output_dir"].as<std::string>());
  }
  if (config["enable_live_stream"]) {
    tc.enable_live_stream = config["enable_live_stream"].as<bool>();
  } else if (config["publish_throttled"]) {
    // Backward compatibility: map old key to new key
    tc.enable_live_stream = config["publish_throttled"].as<bool>();
  }
  if (config["timer_period_ms"]) {
    tc.timer_period_ms = config["timer_period_ms"].as<double>();
  }

  if (config["topics"]) {
    for (const auto& node : config["topics"]) {
      TopicRule rule;
      if (node["topic"]) {
        rule.topic = node["topic"].as<std::string>();
      }
      if (node["output_topic"]) {
        rule.output_topic = node["output_topic"].as<std::string>();
      } else {
        rule.output_topic = rule.topic;
      }
      if (node["hz"]) {
        rule.hz = node["hz"].as<double>();
      }
      if (node["queue_size"]) {
        rule.queue_size = node["queue_size"].as<int>();
      }
      if (node["write_all_buffered"]) {
        rule.write_all_buffered = node["write_all_buffered"].as<bool>();
      }
      tc.topics.push_back(rule);
    }
  }

  return tc;
}
