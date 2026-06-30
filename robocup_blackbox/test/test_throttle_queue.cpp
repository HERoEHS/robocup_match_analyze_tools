#include <gtest/gtest.h>
#include "robocup_blackbox/throttle_queue.hpp"

TEST(ThrottleQueue, BasicPushPop) {
  ThrottleQueue q("/test", 10.0, 10);
  rclcpp::Time t1(0, 0);
  rclcpp::Time t2(0, 50000000);
  rclcpp::Time t3(0, 100000000);

  q.push({t1, std::vector<uint8_t>{1}, "std_msgs/msg/String"});
  q.push({t2, std::vector<uint8_t>{2}, "std_msgs/msg/String"});
  q.push({t3, std::vector<uint8_t>{3}, "std_msgs/msg/String"});

  EXPECT_EQ(q.size(), 3u);

  SerializedMessage out;
  bool popped = q.pop(out);
  EXPECT_TRUE(popped);
  EXPECT_EQ(out.data[0], 3);
}

TEST(ThrottleQueue, PopFrontPreservesArrivalOrder) {
  ThrottleQueue q("/test", 10.0, 10);
  rclcpp::Time t1(0, 0);
  rclcpp::Time t2(0, 50000000);
  rclcpp::Time t3(0, 100000000);

  q.push({t1, std::vector<uint8_t>{1}, "std_msgs/msg/String"});
  q.push({t2, std::vector<uint8_t>{2}, "std_msgs/msg/String"});
  q.push({t3, std::vector<uint8_t>{3}, "std_msgs/msg/String"});

  SerializedMessage out;
  ASSERT_TRUE(q.popFront(out));
  EXPECT_EQ(out.data[0], 1);
  ASSERT_TRUE(q.popFront(out));
  EXPECT_EQ(out.data[0], 2);
  ASSERT_TRUE(q.popFront(out));
  EXPECT_EQ(out.data[0], 3);
  EXPECT_FALSE(q.popFront(out));
}

TEST(ThrottleQueue, HzGate) {
  ThrottleQueue q("/test", 10.0, 10);
  rclcpp::Time t0(0, 0);
  rclcpp::Time t005(0, 50000000);
  rclcpp::Time t01(0, 100000000);
  rclcpp::Time t011(0, 110000000);
  rclcpp::Time t015(0, 150000000);

  q.push({t0, std::vector<uint8_t>{1}, "std_msgs/msg/String"});
  SerializedMessage out;
  ASSERT_TRUE(q.pop(out));

  q.push({t005, std::vector<uint8_t>{2}, "std_msgs/msg/String"});
  q.push({t015, std::vector<uint8_t>{3}, "std_msgs/msg/String"});

  EXPECT_FALSE(q.shouldWrite(t01));
  EXPECT_TRUE(q.shouldWrite(t011));
}

TEST(ThrottleQueue, OverflowDropOldest) {
  ThrottleQueue q("/test", 10.0, 2);

  for (int i = 1; i <= 5; ++i) {
    rclcpp::Time ti(0, i * 1000000);
    q.push({ti, std::vector<uint8_t>{static_cast<uint8_t>(i)}, "std_msgs/msg/String"});
  }

  EXPECT_EQ(q.size(), 2u);

  SerializedMessage out;
  bool popped = q.pop(out);
  EXPECT_TRUE(popped);
  EXPECT_EQ(out.data[0], 5);
}

TEST(ThrottleQueue, NoThrottle) {
  ThrottleQueue q("/test", 0.0, 10);
  rclcpp::Time t(0, 100000000);
  EXPECT_TRUE(q.shouldWrite(t));
}
