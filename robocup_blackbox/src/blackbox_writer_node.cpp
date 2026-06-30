#include "robocup_blackbox/blackbox_writer_node.hpp"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <filesystem>
#include <functional>
#include <iomanip>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <rcpputils/filesystem_helper.hpp>
#include <rosbag2_cpp/writer.hpp>
#include <rosbag2_storage/storage_options.hpp>
#include <rosbag2_storage/topic_metadata.hpp>
#include <yaml-cpp/yaml.h>

BlackboxWriterNode::BlackboxWriterNode(const rclcpp::NodeOptions& options)
    : Node("blackbox_writer", options) {
  declare_parameter<std::string>("config_path", "");
  declare_parameter<std::string>("mcap_settings_path", "");
  declare_parameter<std::string>("robot_id", "");
  declare_parameter<bool>("enable_live_stream", false);

  if (!loadAllConfig()) {
    RCLCPP_FATAL(get_logger(), "Failed to load config. Shutting down.");
    return;
  }

  timer_ = create_wall_timer(
      std::chrono::milliseconds(static_cast<int>(topic_config_.timer_period_ms)),
      std::bind(&BlackboxWriterNode::timerCallback, this));

  flush_timer_ = create_wall_timer(
      std::chrono::seconds(static_cast<int>(mcap_config_.force_flush_interval_sec)),
      std::bind(&BlackboxWriterNode::flushCallback, this));

  discover_timer_ = create_wall_timer(
      std::chrono::seconds(1),
      [this]() {
        discoverAndSubscribe();
        if (active_rules_.size() == subs_.size()) {
          RCLCPP_INFO(get_logger(), "All %zu topics subscribed.", subs_.size());
          timer_->cancel();
          timer_->reset();
          timer_ = create_wall_timer(
              std::chrono::milliseconds(static_cast<int>(topic_config_.timer_period_ms)),
              std::bind(&BlackboxWriterNode::timerCallback, this));
          discover_timer_->cancel();
        }
      });

  printStartupBanner();

  start_time_ = this->get_clock()->now();

  if (topic_config_.enable_live_stream) {
    health_pub_ = create_publisher<diagnostic_msgs::msg::DiagnosticArray>(
        "/blackbox/health", rclcpp::QoS(1).reliable());
    health_timer_ = create_wall_timer(
        std::chrono::seconds(1),
        std::bind(&BlackboxWriterNode::publishHealth, this));

    feed_pub_ = create_publisher<std_msgs::msg::String>("/bb/feed", rclcpp::QoS(1).reliable());
    feed_timer_ = create_wall_timer(
        std::chrono::seconds(1),
        std::bind(&BlackboxWriterNode::publishFeed, this));
  }
}

BlackboxWriterNode::~BlackboxWriterNode() {
  if (writer_) {
    writer_->close();
  }
}

bool BlackboxWriterNode::loadAllConfig() {
  std::string config_path = get_parameter("config_path").as_string();
  if (config_path.empty()) {
    RCLCPP_ERROR(get_logger(), "Parameter 'config_path' is required.");
    return false;
  }

  topic_config_ = loadTopicConfig(config_path);

  // ROS parameter takes precedence over YAML
  topic_config_.enable_live_stream = this->get_parameter("enable_live_stream").as_bool();

  std::string robot_id = get_parameter("robot_id").as_string();
  if (!robot_id.empty()) {
    topic_config_.robot_id = robot_id;
  }
  if (topic_config_.robot_id.empty()) {
    RCLCPP_ERROR(get_logger(), "robot_id must be set (config or param).");
    return false;
  }

  std::string mcap_path = get_parameter("mcap_settings_path").as_string();
  if (!mcap_path.empty()) {
    YAML::Node mcap_yaml = YAML::LoadFile(mcap_path);
    if (mcap_yaml["mcap"]) {
      const auto& node = mcap_yaml["mcap"];
      if (node["chunk_size"]) {
        mcap_config_.chunk_size = node["chunk_size"].as<size_t>();
      }
      if (node["compression"]) {
        mcap_config_.compression = node["compression"].as<std::string>();
      }
      if (node["compression_level"]) {
        mcap_config_.compression_level = node["compression_level"].as<int>();
      }
      if (node["force_flush_interval_sec"]) {
        mcap_config_.force_flush_interval_sec = node["force_flush_interval_sec"].as<double>();
      }
      if (node["max_file_size"]) {
        mcap_config_.max_file_size = node["max_file_size"].as<size_t>();
      }
      if (node["use_message_stamps"]) {
        mcap_config_.use_message_stamps = node["use_message_stamps"].as<bool>();
      }
      if (node["max_bag_count"]) {
        mcap_config_.max_bag_count = node["max_bag_count"].as<size_t>();
      }
    }
  }

  std::string output_dir = resolveHomePath(topic_config_.output_dir);
  std::filesystem::create_directories(output_dir);

  cleanupOldBags(output_dir);

  std::string filename = makeTimestampFilename(topic_config_.robot_id, output_dir);

  writer_ = std::make_unique<McapWriter>();
  if (!writer_->open(filename, topic_config_.robot_id, mcap_config_)) {
    RCLCPP_ERROR(get_logger(), "Failed to open mcap: %s", filename.c_str());
    return false;
  }

  for (const auto& rule : topic_config_.topics) {
    if (rule.hz < 0.0) continue;
    active_rules_.push_back(rule);
    queues_.push_back(std::make_unique<ThrottleQueue>(
        rule.output_topic.empty() ? rule.topic : rule.output_topic,
        rule.hz, rule.queue_size));
    RCLCPP_INFO(
        get_logger(),
        "Queued topic %s at %.1f Hz (queue %zu%s)",
        rule.topic.c_str(),
        rule.hz,
        rule.queue_size,
        rule.write_all_buffered ? ", write_all_buffered" : "");
  }

  return true;
}

void BlackboxWriterNode::discoverAndSubscribe() {
  auto topic_map = get_topic_names_and_types();

  for (size_t i = 0; i < active_rules_.size(); ++i) {
    const auto& rule = active_rules_[i];
    if (subs_.count(rule.topic)) continue;

    auto it = topic_map.find(rule.topic);
    if (it == topic_map.end()) continue;

    std::string type_name = it->second.empty() ? "" : it->second[0];
    if (type_name.empty()) continue;

    std::string out_topic = rule.output_topic.empty() ? rule.topic : rule.output_topic;

    std::string rule_topic = rule.topic;
    auto callback = [this, rule_topic, out_topic, type_name](
                        std::shared_ptr<rclcpp::SerializedMessage> msg) {
      this->onGenericMessage(rule_topic, out_topic, type_name, msg);
    };

    // QoS fix: auto-detect publisher QoS (prevent missing BEST_EFFORT publishers)
    // Fall back to BEST_EFFORT if publisher not found
    rclcpp::QoS sub_qos = rclcpp::QoS(10).best_effort();
    auto publishers = get_publishers_info_by_topic(rule.topic);
    if (!publishers.empty()) {
      bool all_reliable = true;
      bool all_transient_local = true;
      for (const auto& pub : publishers) {
        const auto& pub_qos = pub.qos_profile();
        if (pub_qos.reliability() != rclcpp::ReliabilityPolicy::Reliable) all_reliable = false;
        if (pub_qos.durability() != rclcpp::DurabilityPolicy::TransientLocal) all_transient_local = false;
      }
      sub_qos.reliability(all_reliable ? rclcpp::ReliabilityPolicy::Reliable
                                       : rclcpp::ReliabilityPolicy::BestEffort);
      sub_qos.durability(all_transient_local ? rclcpp::DurabilityPolicy::TransientLocal
                                             : rclcpp::DurabilityPolicy::Volatile);
    }

    auto sub = create_generic_subscription(rule.topic, type_name, sub_qos, callback);
    subs_[rule.topic] = sub;
    RCLCPP_INFO(get_logger(), "Subscribed to %s [%s] (%s)", rule.topic.c_str(), type_name.c_str(),
                sub_qos.reliability() == rclcpp::ReliabilityPolicy::Reliable ? "RELIABLE" : "BEST_EFFORT");

    if (topic_config_.enable_live_stream && !throttle_pubs_.count(rule.topic)) {
      std::string throttled_topic = rule.topic + "_throttled";
      auto pub = create_generic_publisher(throttled_topic, type_name, rclcpp::QoS(10));
      throttle_pubs_[rule.topic] = pub;
      RCLCPP_INFO(get_logger(), "Created throttled publisher for %s [%s]",
                 throttled_topic.c_str(), type_name.c_str());
    }
  }
}

void BlackboxWriterNode::onGenericMessage(
    const std::string&, const std::string& output_topic,
    const std::string& type_name, std::shared_ptr<rclcpp::SerializedMessage> msg) {
  rclcpp::Time now = rclcpp::Clock().now();

  const auto& rcl_msg = msg->get_rcl_serialized_message();
  std::vector<uint8_t> buffer(rcl_msg.buffer, rcl_msg.buffer + rcl_msg.buffer_length);

  SerializedMessage smsg{now, std::move(buffer), type_name};

  for (auto& q : queues_) {
    if (q->topic() == output_topic) {
      q->push(smsg);
      break;
    }
  }
}

void BlackboxWriterNode::timerCallback() {
  if (!writer_) return;

  rclcpp::Time now = rclcpp::Clock().now();

  for (size_t i = 0; i < queues_.size(); ++i) {
    auto& q = queues_[i];
    const auto& rule = active_rules_[i];
    if (!q->shouldWrite(now)) continue;

    auto write_message = [this, &rule, &q](const SerializedMessage& msg) {
      writer_->write(q->topic(), msg.stamp, msg.data.data(), msg.data.size(), msg.type_name);

      if (!topic_config_.enable_live_stream) {
        return;
      }

      auto it = throttle_pubs_.find(rule.topic);
      if (it == throttle_pubs_.end()) {
        return;
      }

      rcl_serialized_message_t rcl_msg;
      rcl_msg.buffer = const_cast<uint8_t*>(msg.data.data());
      rcl_msg.buffer_length = msg.data.size();
      rcl_msg.buffer_capacity = msg.data.size();
      rcl_msg.allocator = rcl_get_default_allocator();
      rclcpp::SerializedMessage serialized_msg(rcl_msg);
      it->second->publish(serialized_msg);
    };

    SerializedMessage msg;
    if (rule.write_all_buffered) {
      while (q->popFront(msg)) {
        write_message(msg);
      }
    } else {
      if (!q->pop(msg)) continue;
      write_message(msg);
    }
  }
}

void BlackboxWriterNode::flushCallback() {
  if (writer_) {
    writer_->flush();
    RCLCPP_DEBUG(get_logger(), "Periodic mcap flush");
  }
}

void BlackboxWriterNode::publishHealth() {
  if (!health_pub_) return;

  diagnostic_msgs::msg::DiagnosticArray diag_array;
  diag_array.header.stamp = rclcpp::Time(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::system_clock::now().time_since_epoch())
          .count(),
      RCL_ROS_TIME);
  diag_array.header.frame_id = "";

  {
    diagnostic_msgs::msg::DiagnosticStatus writer_status;
    writer_status.name = "mcap_writer";
    writer_status.hardware_id = topic_config_.robot_id;
    if (writer_) {
      // "recording" only if data was actually written since the last tick;
      // a writer that is open but idle (no topics flowing) is not recording.
      uint64_t written = writer_->messagesWritten();
      bool recording = written > last_health_msgs_written_;
      last_health_msgs_written_ = written;

      writer_status.level = diagnostic_msgs::msg::DiagnosticStatus::OK;
      writer_status.message = recording ? "recording" : "idle (no data written)";

      diagnostic_msgs::msg::KeyValue kv;
      kv.key = "file_size";
      kv.value = std::to_string(writer_->fileSize());
      writer_status.values.push_back(kv);

      diagnostic_msgs::msg::KeyValue kv_recording;
      kv_recording.key = "recording";
      kv_recording.value = recording ? "true" : "false";
      writer_status.values.push_back(kv_recording);

      diagnostic_msgs::msg::KeyValue kv_written;
      kv_written.key = "messages_written";
      kv_written.value = std::to_string(written);
      writer_status.values.push_back(kv_written);
    } else {
      writer_status.level = diagnostic_msgs::msg::DiagnosticStatus::ERROR;
      writer_status.message = "writer not open";
    }
    diag_array.status.push_back(writer_status);
  }

  rclcpp::Time health_now = rclcpp::Clock().now();
  for (const auto& q : queues_) {
    diagnostic_msgs::msg::DiagnosticStatus queue_status;
    queue_status.name = "throttle_" + q->topic();
    queue_status.hardware_id = topic_config_.robot_id;

    double age_sec = -1.0;
    if (q->receivedCount() == 0) {
      // Never received a single message on this topic.
      queue_status.level = diagnostic_msgs::msg::DiagnosticStatus::ERROR;
      queue_status.message = "no data received";
    } else {
      age_sec = (health_now - q->lastRecvTime()).seconds();
      // Expected period from target hz; untimed (hz<=0) topics assume ~2 Hz.
      double hz = q->targetHz();
      double expected = (hz > 0.0) ? (1.0 / hz) : 0.5;
      // Allow generous slack: 5x the expected period, but at least 1 s grace.
      double stale_threshold = std::max(5.0 * expected, 1.0);
      if (age_sec > stale_threshold) {
        queue_status.level = diagnostic_msgs::msg::DiagnosticStatus::WARN;
        std::stringstream ms;
        ms << std::fixed << std::setprecision(1)
           << "stale (no data for " << age_sec << "s)";
        queue_status.message = ms.str();
      } else {
        queue_status.level = diagnostic_msgs::msg::DiagnosticStatus::OK;
        queue_status.message = "running";
      }
    }

    diagnostic_msgs::msg::KeyValue kv;
    kv.key = "queue_size";
    kv.value = std::to_string(q->size());
    queue_status.values.push_back(kv);

    diagnostic_msgs::msg::KeyValue kv_count;
    kv_count.key = "received_count";
    kv_count.value = std::to_string(q->receivedCount());
    queue_status.values.push_back(kv_count);

    diagnostic_msgs::msg::KeyValue kv_age;
    kv_age.key = "last_msg_age_sec";
    kv_age.value = (age_sec < 0.0) ? "N/A" : std::to_string(age_sec);
    queue_status.values.push_back(kv_age);

    diag_array.status.push_back(queue_status);
  }

  {
    diagnostic_msgs::msg::DiagnosticStatus wd_status;
    wd_status.name = "watchdog";
    wd_status.hardware_id = topic_config_.robot_id;
#ifdef WATCHDOG_INSTALLED
    wd_status.level = diagnostic_msgs::msg::DiagnosticStatus::OK;
    wd_status.message = "installed";
#else
    wd_status.level = diagnostic_msgs::msg::DiagnosticStatus::WARN;
    wd_status.message = "not installed";
#endif
    diag_array.status.push_back(wd_status);
  }

  health_pub_->publish(diag_array);
}

void BlackboxWriterNode::publishFeed() {
  if (!feed_pub_) return;

  std_msgs::msg::String msg;
  std::stringstream ss;
  ss << std::fixed << std::setprecision(1);

  double duration = (this->get_clock()->now() - start_time_).seconds();
  size_t total_msgs = 0;
  for (auto& q : queues_) {
    total_msgs += q->size();
  }

  ss << "{"
     << "\"robot_id\":\"" << topic_config_.robot_id << "\","
     << "\"file\":\"" << (writer_ ? writer_->currentFileName() : "") << "\","
     << "\"size_mb\":" << (writer_ ? writer_->fileSize() / (1024.0 * 1024.0) : 0.0) << ","
     << "\"topics\":" << subs_.size() << ","
     << "\"duration_sec\":" << duration << ","
     << "\"total_msgs\":" << total_msgs;

  if (!queues_.empty()) {
    ss << ",\"topic_counts\":" << "[";
    bool first = true;
    for (auto& q : queues_) {
      if (!first) ss << ",";
      ss << "{\"topic\":\"" << q->topic() << "\",\"count\":" << q->size() << "}";
      first = false;
    }
    ss << "]";
  }

  ss << "}";

  msg.data = ss.str();
  feed_pub_->publish(msg);
}

void BlackboxWriterNode::printStartupBanner() {
  const std::string sep(52, '-');

  RCLCPP_INFO(get_logger(), "%s", sep.c_str());
  RCLCPP_INFO(get_logger(), "  RoboCup Blackbox");
  RCLCPP_INFO(get_logger(), "%s", sep.c_str());
  RCLCPP_INFO(get_logger(), "  Robot ID       : %s", topic_config_.robot_id.c_str());
  RCLCPP_INFO(get_logger(), "  Output Dir     : %s", topic_config_.output_dir.c_str());
  RCLCPP_INFO(get_logger(), "  Live Stream    : %s",
              topic_config_.enable_live_stream ? "enabled" : "disabled");
  RCLCPP_INFO(get_logger(), "%s", sep.c_str());
  RCLCPP_INFO(get_logger(), "  MCAP Settings");
  if (mcap_config_.compression == "none" || mcap_config_.compression.empty()) {
    RCLCPP_INFO(get_logger(), "  Compression    : none");
  } else {
    RCLCPP_INFO(get_logger(), "  Compression    : %s  (level %d)",
                mcap_config_.compression.c_str(), mcap_config_.compression_level);
  }
  RCLCPP_INFO(get_logger(), "  Max File Size  : %zu MB",
              mcap_config_.max_file_size / (1024 * 1024));
  RCLCPP_INFO(get_logger(), "  Chunk Size     : %zu KB", mcap_config_.chunk_size / 1024);
  RCLCPP_INFO(get_logger(), "  Flush Interval : %.0f sec", mcap_config_.force_flush_interval_sec);
  RCLCPP_INFO(get_logger(), "  Msg Timestamps : %s",
              mcap_config_.use_message_stamps ? "header.stamp" : "receive_time");
  if (mcap_config_.max_bag_count > 0) {
    RCLCPP_INFO(get_logger(), "  Max Bag Count  : %zu  (oldest auto-deleted on startup)",
                mcap_config_.max_bag_count);
  } else {
    RCLCPP_INFO(get_logger(), "  Max Bag Count  : unlimited");
  }
  RCLCPP_INFO(get_logger(), "%s", sep.c_str());

  size_t active_count = 0;
  for (const auto& rule : topic_config_.topics) {
    if (rule.hz >= 0.0) ++active_count;
  }
  RCLCPP_INFO(get_logger(), "  Topics  (%zu active / %zu configured)",
              active_count, topic_config_.topics.size());

  for (const auto& rule : topic_config_.topics) {
    if (rule.hz < 0.0) {
      RCLCPP_INFO(get_logger(), "    %-44s  [excluded]", rule.topic.c_str());
    } else if (rule.hz == 0.0) {
      RCLCPP_INFO(
          get_logger(),
          "    %-44s  unlimited  [q:%zu%s]",
          rule.topic.c_str(),
          rule.queue_size,
          rule.write_all_buffered ? ", all" : "");
    } else {
      RCLCPP_INFO(
          get_logger(),
          "    %-44s  %6.1f Hz  [q:%zu%s]",
          rule.topic.c_str(),
          rule.hz,
          rule.queue_size,
          rule.write_all_buffered ? ", all" : "");
    }
  }

  RCLCPP_INFO(get_logger(), "%s", sep.c_str());
}

void BlackboxWriterNode::cleanupOldBags(const std::string& output_dir) {
  if (mcap_config_.max_bag_count == 0) return;

  const std::string prefix = topic_config_.robot_id + "_";
  const std::string mcap_suffix = ".mcap";

  // Collect only base bags (exclude split files .mcap.1, .mcap.2, etc.)
  std::vector<std::filesystem::path> base_bags;
  try {
    for (const auto& entry : std::filesystem::directory_iterator(output_dir)) {
      const std::string name = entry.path().filename().string();
      if (name.rfind(prefix, 0) != 0) continue;
      if (name.size() <= mcap_suffix.size()) continue;
      if (name.substr(name.size() - mcap_suffix.size()) != mcap_suffix) continue;
      base_bags.push_back(entry.path());
    }
  } catch (const std::exception& e) {
    RCLCPP_WARN(get_logger(), "cleanupOldBags: %s", e.what());
    return;
  }

  if (base_bags.size() < mcap_config_.max_bag_count) return;

  // Filenames contain timestamps, so alphabetical sort equals chronological order
  std::sort(base_bags.begin(), base_bags.end());

  // Delete excess + 1 to make room for the new bag
  const size_t to_delete = base_bags.size() - mcap_config_.max_bag_count + 1;
  for (size_t i = 0; i < to_delete; ++i) {
    const std::string base = base_bags[i].string();
    try {
      std::filesystem::remove_all(base_bags[i]);
      RCLCPP_INFO(get_logger(), "Removed old bag: %s", base.c_str());
      // Also delete split files (.mcap.1, .mcap.2, ...)
      for (size_t j = 1; ; ++j) {
        std::filesystem::path split = base + "." + std::to_string(j);
        if (!std::filesystem::exists(split)) break;
        std::filesystem::remove_all(split);
        RCLCPP_INFO(get_logger(), "Removed split: %s", split.string().c_str());
      }
    } catch (const std::exception& e) {
      RCLCPP_WARN(get_logger(), "Failed to remove %s: %s", base.c_str(), e.what());
    }
  }
}

std::string BlackboxWriterNode::makeTimestampFilename(const std::string& robot_id,
                                                     const std::string& output_dir) {
  auto now = std::chrono::system_clock::now();
  auto t = std::chrono::system_clock::to_time_t(now);
  std::stringstream ss;
  ss << output_dir << "/" << robot_id << "_";
  ss << std::put_time(std::localtime(&t), "%Y%m%d_%H%M%S");
  ss << ".mcap";
  return ss.str();
}

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<BlackboxWriterNode>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
