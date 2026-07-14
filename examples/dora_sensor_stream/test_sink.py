#!/usr/bin/env python3
"""Decode Forge image messages and report received stream metadata."""

from __future__ import annotations

import argparse
import time
from collections import defaultdict
from pathlib import Path

import yaml
from dora import Node
from forge_msgs import CompressedImage, Image


def _decode(value: object) -> tuple[str, int, int, str]:
    try:
        image = Image.from_arrow(value)
        return "Image", image.width, image.height, image.encoding
    except Exception:
        image = CompressedImage.from_arrow(value)
        decoded = image.to_numpy()
        height, width = decoded.shape[:2]
        return "CompressedImage", width, height, image.format


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="test_sink.yaml")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    print_every = max(1, int(config.get("print_every", 30)))
    counts: dict[str, int] = defaultdict(int)

    for event in Node():
        if event["type"] == "STOP":
            break
        if event["type"] != "INPUT":
            continue
        topic = str(event["id"])
        counts[topic] += 1
        try:
            kind, width, height, encoding = _decode(event["value"])
        except Exception as exc:
            print(f"decode_error topic={topic} count={counts[topic]} error={exc}", flush=True)
            continue
        if counts[topic] == 1 or counts[topic] % print_every == 0:
            print(
                f"topic={topic} count={counts[topic]} type={kind} "
                f"size={width}x{height} encoding={encoding} received_at={time.time():.6f}",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
