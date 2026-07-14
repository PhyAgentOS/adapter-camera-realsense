#!/usr/bin/env python3
"""Capture one sample without Dora."""

from __future__ import annotations

import argparse

from forge_devices_realsense_camera.config import RealSenseConfig
from forge_devices_realsense_camera.snapshot import run_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture one RealSense sample")
    parser.add_argument("--config", default="config/sensor.example.yaml")
    parser.add_argument("--output", default="sample_output/capture.jpg")
    parser.add_argument("--all-streams", action="store_true")
    args = parser.parse_args()
    return run_snapshot(
        RealSenseConfig.from_yaml_path(args.config),
        args.output,
        jpeg_quality=None,
        all_streams=args.all_streams,
    )


if __name__ == "__main__":
    raise SystemExit(main())
