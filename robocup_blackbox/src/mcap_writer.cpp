#include "robocup_blackbox/mcap_writer.hpp"

#include <cstring>
#include <filesystem>
#include <fstream>

#include <rosbag2_cpp/writer.hpp>
#include <rosbag2_storage/storage_options.hpp>
#include <rosbag2_storage/topic_metadata.hpp>

McapWriter::McapWriter() = default;

McapWriter::~McapWriter() {
  close();
}

bool McapWriter::open(const std::string& filename, const std::string& robot_id,
                      const McapConfig& config) {
  close();

  robot_id_ = robot_id;
  config_ = config;
  base_filename_ = filename;
  current_filename_ = filename;
  current_file_size_ = 0;
  split_count_ = 0;
  created_topics_.clear();
  storage_config_path_ = buildStorageConfigFile();  // generate yaml if compression is enabled

  try {
    writer_ = std::make_unique<rosbag2_cpp::Writer>();

    rosbag2_storage::StorageOptions storage_options;
    storage_options.uri = current_filename_;
    storage_options.storage_id = "mcap";
    storage_options.max_bagfile_size = 0;
    if (!storage_config_path_.empty()) {
      storage_options.storage_config_uri = storage_config_path_;  // link compression config
    }

    writer_->open(storage_options);
  } catch (const std::exception& e) {
    return false;
  }

  return true;
}

std::string McapWriter::buildStorageConfigFile() const {
  std::string comp;
  if (config_.compression == "zstd") {
    comp = "Zstd";
  } else if (config_.compression == "lz4") {
    comp = "Lz4";
  } else {
    return "";  // none / unspecified → no compression (preserves existing behavior)
  }

  // mcap CompressionLevel enum mapping
  const char* level = "Default";
  if (config_.compression_level <= 1) {
    level = "Fastest";
  } else if (config_.compression_level == 2) {
    level = "Fast";
  } else if (config_.compression_level == 3) {
    level = "Default";
  } else if (config_.compression_level == 4) {
    level = "Slow";
  } else {
    level = "Slowest";
  }

  std::filesystem::path dir = std::filesystem::path(base_filename_).parent_path();
  std::filesystem::path cfg = dir / (".bb_mcap_storage_" + robot_id_ + ".yaml");
  std::ofstream f(cfg);
  if (!f) {
    return "";
  }
  f << "compression: \"" << comp << "\"\n"
    << "compressionLevel: \"" << level << "\"\n"
    << "chunkSize: " << config_.chunk_size << "\n";
  return cfg.string();
}

void McapWriter::close() {
  if (writer_) {
    writer_->close();
    writer_.reset();
  }
}

bool McapWriter::write(const std::string& topic, const rclcpp::Time& stamp,
                       const uint8_t* data, size_t len,
                       const std::string& type_name) {
  if (!writer_) {
    return false;
  }

  if (needsSplit()) {
    splitFile();
  }

  const std::string channel = makeChannelName(topic);

  if (created_topics_.find(channel) == created_topics_.end()) {
    rosbag2_storage::TopicMetadata topic_meta;
    topic_meta.name = channel;
    topic_meta.type = type_name;
    topic_meta.serialization_format = "cdr";
    writer_->create_topic(topic_meta);
    created_topics_.insert(channel);
  }

  auto msg = std::make_shared<rclcpp::SerializedMessage>(len);
  auto& rcl_msg = msg->get_rcl_serialized_message();
  std::memcpy(rcl_msg.buffer, data, len);
  rcl_msg.buffer_length = len;

  rclcpp::Time msg_time = config_.use_message_stamps ? stamp : rclcpp::Clock().now();

  try {
    writer_->write(msg, channel, type_name, msg_time);
  } catch (const std::exception& e) {
    return false;
  }

  current_file_size_ += len;
  ++messages_written_;

  return true;
}

void McapWriter::flush() {}

size_t McapWriter::fileSize() const {
  if (std::filesystem::is_directory(current_filename_)) {
    for (const auto& entry : std::filesystem::directory_iterator(current_filename_)) {
      if (entry.is_regular_file() && entry.path().extension() == ".mcap") {
        return entry.file_size();
      }
    }
  }
  return current_file_size_;
}

bool McapWriter::needsSplit() const {
  if (config_.max_file_size == 0) {
    return false;
  }
  return current_file_size_ >= config_.max_file_size;
}

void McapWriter::splitFile() {
  close();

  ++split_count_;
  current_filename_ = makeSplitFilename(base_filename_, split_count_);
  current_file_size_ = 0;
  created_topics_.clear();

  try {
    writer_ = std::make_unique<rosbag2_cpp::Writer>();

    rosbag2_storage::StorageOptions storage_options;
    storage_options.uri = current_filename_;
    storage_options.storage_id = "mcap";
    storage_options.max_bagfile_size = 0;
    if (!storage_config_path_.empty()) {
      storage_options.storage_config_uri = storage_config_path_;  // retain compression after split
    }

    writer_->open(storage_options);
  } catch (const std::exception& e) {
    writer_.reset();
  }
}

std::string McapWriter::makeSplitFilename(const std::string& base,
                                            size_t split_idx) const {
  return base + "." + std::to_string(split_idx);
}

std::string McapWriter::makeChannelName(const std::string& topic) const {
  if (!topic.empty() && topic.front() == '/') {
    return robot_id_ + topic;
  }
  return robot_id_ + "/" + topic;
}
