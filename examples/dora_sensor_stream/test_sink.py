#!/usr/bin/env python3
"""Decode Forge point-cloud and image messages and report stream metadata."""

from __future__ import annotations

import argparse
import time
from collections import defaultdict
from pathlib import Path

import yaml
from dora import Node
from forge_msgs import CompressedImage, Image, PointCloudView


def _decode(topic: str, value: object) -> str:
    if topic == "point_cloud":
        point_cloud = PointCloudView.from_arrow(value)
        return (
            f"type=PointCloud size={point_cloud.width}x{point_cloud.height} "
            f"point_count={point_cloud.point_count} is_dense={point_cloud.is_dense} "
            f"has_rgb={point_cloud.has_rgb}"
        )

    try:
        image = Image.from_arrow(value)
        kind, width, height, encoding = (
            "Image",
            image.width,
            image.height,
            image.encoding,
        )
    except Exception:
        image = CompressedImage.from_arrow(value)
        decoded = image.to_numpy()
        height, width = decoded.shape[:2]
        kind, encoding = "CompressedImage", image.format
    return f"type={kind} size={width}x{height} encoding={encoding}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="test_sink.yaml")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    print_every = max(1, int(config.get("print_every", 30)))
    min_frames = int(config.get("min_frames", 1))
    if min_frames < 1:
        raise ValueError("min_frames must be positive")
    expected = list(config.get("expected_inputs", []))
    counts: dict[str, int] = defaultdict(int)

    for event in Node():
        if event["type"] == "STOP":
            break
        if event["type"] == "ERROR":
            raise RuntimeError(event.get("error", "Dora error"))
        if event["type"] != "INPUT":
            continue
        topic = str(event["id"])
        details = _decode(topic, event["value"])
        counts[topic] += 1
        if counts[topic] == 1 or counts[topic] % print_every == 0:
            print(
                f"topic={topic} count={counts[topic]} {details} "
                f"received_at={time.time():.6f}",
                flush=True,
            )
    missing = [topic for topic in expected if counts[topic] < min_frames]
    if missing or sum(counts.values()) < min_frames:
        raise RuntimeError(
            f"insufficient valid frames: counts={dict(counts)}, missing={missing}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
