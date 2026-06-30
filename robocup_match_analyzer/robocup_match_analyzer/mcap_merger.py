"""Utilities for merging rosbag2 MCAP bags into one downloadable archive."""
from __future__ import annotations

from dataclasses import dataclass
import heapq
import re
import shutil
import zipfile
from pathlib import Path
from typing import Iterable

import rosbag2_py


_SESSION_RE = re.compile(r"(\d{8}_\d{6})")


@dataclass(frozen=True)
class MergeSummary:
    input_paths: list[Path]
    output_uri: Path
    topic_count: int
    message_count: int
    first_timestamp_ns: int | None
    last_timestamp_ns: int | None

    @property
    def duration_sec(self) -> float:
        if self.first_timestamp_ns is None or self.last_timestamp_ns is None:
            return 0.0
        return max(0.0, (self.last_timestamp_ns - self.first_timestamp_ns) / 1e9)


def normalize_input_paths(paths: Iterable[Path | str]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def suggest_merged_name(paths: Iterable[Path | str]) -> str:
    normalized = normalize_input_paths(paths)
    session_keys = {
        match.group(1)
        for path in normalized
        if (match := _SESSION_RE.search(path.name))
    }
    if len(session_keys) == 1:
        return f"{next(iter(session_keys))}_merged"

    if not normalized:
        return "merged_session"

    first = normalized[0].name
    if first.endswith(".mcap"):
        first = first[:-5]
    first = re.sub(r"\.\d+$", "", first)
    return f"{first}_merged"


def merge_bags(input_paths: Iterable[Path | str], output_uri: Path | str) -> MergeSummary:
    resolved_inputs = normalize_input_paths(input_paths)
    if not resolved_inputs:
        raise ValueError("No input bags provided.")

    output_path = Path(output_uri).expanduser().resolve()
    _prepare_output_uri(output_path)

    readers: list[tuple[Path, rosbag2_py.SequentialReader, list[rosbag2_py.TopicMetadata]]] = []
    writer: rosbag2_py.SequentialWriter | None = None

    try:
        for path in resolved_inputs:
            if not path.exists():
                raise FileNotFoundError(f"Input bag not found: {path}")
            reader = _open_reader(path)
            readers.append((path, reader, list(reader.get_all_topics_and_types())))

        writer = rosbag2_py.SequentialWriter()
        writer.open(
            rosbag2_py.StorageOptions(uri=str(output_path), storage_id="mcap"),
            rosbag2_py.ConverterOptions("", ""),
        )

        topic_count = _register_topics(writer, readers)
        message_count, first_ts, last_ts = _merge_messages(writer, readers)

        return MergeSummary(
            input_paths=resolved_inputs,
            output_uri=output_path,
            topic_count=topic_count,
            message_count=message_count,
            first_timestamp_ns=first_ts,
            last_timestamp_ns=last_ts,
        )
    finally:
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
        for _, reader, _ in readers:
            try:
                reader.close()
            except Exception:
                pass


def create_download_zip(bag_uri: Path | str, zip_path: Path | str) -> Path:
    bag_path = Path(bag_uri).expanduser().resolve()
    archive_path = Path(zip_path).expanduser().resolve()
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        root = bag_path.parent
        for file_path in sorted(bag_path.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, arcname=str(file_path.relative_to(root)))

    return archive_path


def _prepare_output_uri(output_uri: Path) -> None:
    output_uri.parent.mkdir(parents=True, exist_ok=True)

    for path in [output_uri, *sorted(output_uri.parent.glob(f"{output_uri.name}.[0-9]*"))]:
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def _open_reader(path: Path) -> rosbag2_py.SequentialReader:
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(path), storage_id="mcap"),
        rosbag2_py.ConverterOptions("", ""),
    )
    return reader


def _clone_topic_metadata(topic: rosbag2_py.TopicMetadata) -> rosbag2_py.TopicMetadata:
    return rosbag2_py.TopicMetadata(
        0,
        topic.name,
        topic.type,
        topic.serialization_format,
        topic.offered_qos_profiles,
        topic.type_description_hash,
    )


def _register_topics(
    writer: rosbag2_py.SequentialWriter,
    readers: list[tuple[Path, rosbag2_py.SequentialReader, list[rosbag2_py.TopicMetadata]]],
) -> int:
    registered: dict[str, rosbag2_py.TopicMetadata] = {}

    for path, _, topics in readers:
        for topic in topics:
            current = registered.get(topic.name)
            if current is None:
                metadata = _clone_topic_metadata(topic)
                writer.create_topic(metadata)
                registered[metadata.name] = metadata
                continue

            if current.type != topic.type:
                raise RuntimeError(
                    f"Topic type conflict on {topic.name}: "
                    f"{current.type} vs {topic.type} ({path.name})"
                )
            if current.serialization_format != topic.serialization_format:
                raise RuntimeError(
                    f"Serialization conflict on {topic.name}: "
                    f"{current.serialization_format} vs {topic.serialization_format} "
                    f"({path.name})"
                )
            if (
                current.type_description_hash
                and topic.type_description_hash
                and current.type_description_hash != topic.type_description_hash
            ):
                raise RuntimeError(
                    f"Type description hash conflict on {topic.name}: "
                    f"{current.type_description_hash} vs {topic.type_description_hash} "
                    f"({path.name})"
                )

    return len(registered)


def _merge_messages(
    writer: rosbag2_py.SequentialWriter,
    readers: list[tuple[Path, rosbag2_py.SequentialReader, list[rosbag2_py.TopicMetadata]]],
) -> tuple[int, int | None, int | None]:
    heap: list[tuple[int, int, str, bytes]] = []
    for index, (_, reader, _) in enumerate(readers):
        if reader.has_next():
            topic, data, timestamp = reader.read_next()
            heapq.heappush(heap, (timestamp, index, topic, data))

    message_count = 0
    first_ts: int | None = None
    last_ts: int | None = None

    while heap:
        timestamp, index, topic, data = heapq.heappop(heap)
        writer.write(topic, data, timestamp)

        if first_ts is None:
            first_ts = timestamp
        last_ts = timestamp
        message_count += 1

        _, reader, _ = readers[index]
        if reader.has_next():
            next_topic, next_data, next_timestamp = reader.read_next()
            heapq.heappush(heap, (next_timestamp, index, next_topic, next_data))

    return message_count, first_ts, last_ts
