#include "robocup_blackbox/throttle_queue.hpp"

ThrottleQueue::ThrottleQueue(const std::string& topic, double target_hz, size_t max_queue_size)
    : topic_(topic), target_hz_(target_hz), max_queue_size_(max_queue_size), last_write_time_(rclcpp::Time(0, 0)) {}

void ThrottleQueue::push(const SerializedMessage& msg) {
  buffer_.push_back(msg);
  if (buffer_.size() > max_queue_size_) {
    buffer_.pop_front();
  }
  ++received_count_;
  last_recv_time_ = msg.stamp;
}

bool ThrottleQueue::shouldWrite(const rclcpp::Time& now) const {
  if (target_hz_ <= 0.0) {
    return true;
  }
  double elapsed = (now - last_write_time_).seconds();
  return elapsed > (1.0 / target_hz_);
}

bool ThrottleQueue::pop(SerializedMessage& out) {
  if (buffer_.empty()) {
    return false;
  }
  out = buffer_.back();
  buffer_.clear();
  last_write_time_ = out.stamp;
  return true;
}

bool ThrottleQueue::popFront(SerializedMessage& out) {
  if (buffer_.empty()) {
    return false;
  }
  out = buffer_.front();
  buffer_.pop_front();
  last_write_time_ = out.stamp;
  return true;
}
