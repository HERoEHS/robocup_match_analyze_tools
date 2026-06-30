#pragma once
#include <cstdint>
#include <memory>
#include <string>
#include <unordered_map>
#include <unordered_set>

#include <rclcpp/rclcpp.hpp>

namespace rosbag2_cpp {
class Writer;
}

struct McapConfig {
  size_t chunk_size = 4 * 1024 * 1024;  // 4MB
  std::string compression = "none";     // "zstd" | "lz4" | "none" (default off, explicit opt-in)
  int compression_level = 3;
  double force_flush_interval_sec = 5.0;
  size_t max_file_size = 2ULL * 1024 * 1024 * 1024;  // 2GB
  bool use_message_stamps = true;  // use header.stamp instead of receive time
  size_t max_bag_count = 0;        // max sessions to retain in output_dir (0 = unlimited)
};

class McapWriter {
 public:
  McapWriter();
  ~McapWriter();

  bool open(const std::string& filename, const std::string& robot_id,
            const McapConfig& config);
  void close();

  bool write(const std::string& topic, const rclcpp::Time& stamp,
             const uint8_t* data, size_t len, const std::string& type_name);

  void flush();

  size_t fileSize() const;
  std::string currentFileName() const { return current_filename_; }

  // Cumulative successful write() count. Used to tell "actively recording"
  // (counter growing) from "writer open but idle" (counter flat).
  uint64_t messagesWritten() const { return messages_written_; }

 private:
  std::unique_ptr<rosbag2_cpp::Writer> writer_;
  std::string robot_id_;
  McapConfig config_;
  std::string current_filename_;
  size_t current_file_size_ = 0;
  uint64_t messages_written_ = 0;
  size_t split_count_ = 0;
  std::string base_filename_;
  std::unordered_set<std::string> created_topics_;
  std::string storage_config_path_;  // path to mcap compression config yaml ("" = no compression)

  // Returns "" if compression is none/unspecified (= storage_config_uri not set → preserves default no-compression behavior).
  std::string buildStorageConfigFile() const;

  bool needsSplit() const;
  void splitFile();
  std::string makeSplitFilename(const std::string& base, size_t split_idx) const;
  std::string makeChannelName(const std::string& topic) const;
};
