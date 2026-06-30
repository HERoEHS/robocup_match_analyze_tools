#include <gtest/gtest.h>

#include <filesystem>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rosbag2_cpp/reader.hpp>
#include <std_msgs/msg/string.hpp>

#include "robocup_blackbox/mcap_writer.hpp"

class McapWriterTest : public ::testing::Test {
 protected:
  static void SetUpTestSuite() {
    if (!rclcpp::ok()) {
      rclcpp::init(0, nullptr);
    }
  }

  static void TearDownTestSuite() {
    if (rclcpp::ok()) {
      rclcpp::shutdown();
    }
  }

  std::vector<uint8_t> serializeString(const std::string& text) {
    std_msgs::msg::String msg;
    msg.data = text;

    rclcpp::Serialization<std_msgs::msg::String> serialization;
    rclcpp::SerializedMessage serialized_msg;
    serialization.serialize_message(&msg, &serialized_msg);

    auto& rcl_msg = serialized_msg.get_rcl_serialized_message();
    return std::vector<uint8_t>(rcl_msg.buffer,
                                rcl_msg.buffer + rcl_msg.buffer_length);
  }
};

TEST_F(McapWriterTest, OpenAndWrite) {
  const std::string tmp_file = "/tmp/test_open_and_write.mcap";
  std::filesystem::remove_all(tmp_file);

  McapWriter writer;
  McapConfig config;
  ASSERT_TRUE(writer.open(tmp_file, "test_robot", config));

  auto data = serializeString("hello world");
  rclcpp::Time stamp(1, 0);

  for (int i = 0; i < 10; ++i) {
    ASSERT_TRUE(writer.write("/chatter", stamp, data.data(), data.size(),
                             "std_msgs/msg/String"));
  }

  writer.close();

  ASSERT_TRUE(std::filesystem::exists(tmp_file));
  EXPECT_TRUE(std::filesystem::is_directory(tmp_file));

  bool found_mcap = false;
  for (const auto& entry : std::filesystem::directory_iterator(tmp_file)) {
    if (entry.is_regular_file() && entry.path().extension() == ".mcap") {
      found_mcap = true;
      EXPECT_GT(entry.file_size(), 0u);
      break;
    }
  }
  EXPECT_TRUE(found_mcap);

  std::filesystem::remove_all(tmp_file);
}

TEST_F(McapWriterTest, ChannelNaming) {
  const std::string tmp_file = "/tmp/test_channel_naming.mcap";
  std::filesystem::remove_all(tmp_file);

  McapWriter writer;
  McapConfig config;
  ASSERT_TRUE(writer.open(tmp_file, "test_robot", config));

  auto data = serializeString("channel test");
  rclcpp::Time stamp(1, 0);
  ASSERT_TRUE(writer.write("/tf", stamp, data.data(), data.size(),
                           "std_msgs/msg/String"));

  writer.close();

  std::string mcap_file;
  for (const auto& entry : std::filesystem::directory_iterator(tmp_file)) {
    if (entry.is_regular_file() && entry.path().extension() == ".mcap") {
      mcap_file = entry.path().string();
      break;
    }
  }
  ASSERT_FALSE(mcap_file.empty());

  rosbag2_cpp::Reader reader;
  reader.open(mcap_file);

  ASSERT_TRUE(reader.has_next());
  auto msg = reader.read_next();
  EXPECT_EQ(msg->topic_name, "test_robot/tf");

  reader.close();
  std::filesystem::remove_all(tmp_file);
}

TEST_F(McapWriterTest, FileSplit) {
  const std::string tmp_file = "/tmp/test_file_split.mcap";
  std::filesystem::remove_all(tmp_file);
  for (int i = 1; i <= 10; ++i) {
    std::filesystem::remove_all(tmp_file + "." + std::to_string(i));
  }

  McapWriter writer;
  McapConfig config;
  config.max_file_size = 1024;
  ASSERT_TRUE(writer.open(tmp_file, "test_robot", config));

  auto data = serializeString(
      "this is a long message to force file splitting quickly");
  rclcpp::Time stamp(1, 0);

  for (int i = 0; i < 100; ++i) {
    ASSERT_TRUE(writer.write("/chatter", stamp, data.data(), data.size(),
                             "std_msgs/msg/String"));
  }

  writer.close();

  EXPECT_TRUE(std::filesystem::exists(tmp_file));
  EXPECT_TRUE(std::filesystem::is_directory(tmp_file));

  bool found_split = false;
  for (int i = 1; i <= 10; ++i) {
    std::string split_name = tmp_file + "." + std::to_string(i);
    if (std::filesystem::exists(split_name) &&
        std::filesystem::is_directory(split_name)) {
      found_split = true;
      break;
    }
  }

  EXPECT_TRUE(found_split);

  std::filesystem::remove_all(tmp_file);
  for (int i = 1; i <= 10; ++i) {
    std::filesystem::remove_all(tmp_file + "." + std::to_string(i));
  }
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
