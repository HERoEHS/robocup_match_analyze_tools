#pragma once
#include <rclcpp/rclcpp.hpp>
#include <rclcpp/generic_publisher.hpp>
#include <rclcpp/generic_subscription.hpp>
#include <diagnostic_msgs/msg/diagnostic_array.hpp>
#include <std_msgs/msg/string.hpp>
#include <memory>
#include <map>
#include <string>
#include <vector>

#include "robocup_blackbox/mcap_writer.hpp"
#include "robocup_blackbox/throttle_queue.hpp"
#include "robocup_blackbox/topic_config.hpp"

class BlackboxWriterNode : public rclcpp::Node {
 public:
  explicit BlackboxWriterNode(const rclcpp::NodeOptions& options = rclcpp::NodeOptions());
  ~BlackboxWriterNode();

 private:
  bool loadAllConfig();
  void discoverAndSubscribe();
  void onGenericMessage(const std::string& topic, const std::string& output_topic,
                        const std::string& type_name,
                        std::shared_ptr<rclcpp::SerializedMessage> msg);
  void timerCallback();
  void flushCallback();
  void splitCallback();
  void publishHealth();
  void publishFeed();
  void cleanupOldBags(const std::string& output_dir);
  void printStartupBanner();
  static std::string makeTimestampFilename(const std::string& robot_id,
                                           const std::string& output_dir);

  TopicConfig topic_config_;
  McapConfig mcap_config_;
  std::unique_ptr<McapWriter> writer_;
  rclcpp::Time start_time_;
  uint64_t last_health_msgs_written_ = 0;  // write count at previous health tick

  std::vector<TopicRule> active_rules_;
  std::vector<std::unique_ptr<ThrottleQueue>> queues_;

  std::map<std::string, rclcpp::GenericSubscription::SharedPtr> subs_;
  std::map<std::string, rclcpp::GenericPublisher::SharedPtr> throttle_pubs_;
  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::TimerBase::SharedPtr flush_timer_;
  rclcpp::TimerBase::SharedPtr split_timer_;
  rclcpp::TimerBase::SharedPtr health_timer_;
  rclcpp::TimerBase::SharedPtr discover_timer_;
  rclcpp::TimerBase::SharedPtr feed_timer_;

  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr health_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr feed_pub_;
};
