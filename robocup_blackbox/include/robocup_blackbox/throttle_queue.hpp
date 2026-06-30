#pragma once
#include <deque>
#include <vector>
#include <string>
#include <rclcpp/rclcpp.hpp>

struct SerializedMessage {
  rclcpp::Time stamp;
  std::vector<uint8_t> data;
  std::string type_name;
};

class ThrottleQueue {
public:
  ThrottleQueue(const std::string& topic, double target_hz, size_t max_queue_size);

  void push(const SerializedMessage& msg);
  bool shouldWrite(const rclcpp::Time& now) const;
  bool pop(SerializedMessage& out);
  bool popFront(SerializedMessage& out);

  size_t size() const { return buffer_.size(); }
  const std::string& topic() const { return topic_; }

  // Liveness tracking (survives buffer drain, unlike size()).
  size_t receivedCount() const { return received_count_; }
  rclcpp::Time lastRecvTime() const { return last_recv_time_; }
  double targetHz() const { return target_hz_; }

private:
  std::string topic_;
  double target_hz_;
  size_t max_queue_size_;
  std::deque<SerializedMessage> buffer_;
  rclcpp::Time last_write_time_;
  size_t received_count_{0};
  rclcpp::Time last_recv_time_{rclcpp::Time(0, 0)};
};
