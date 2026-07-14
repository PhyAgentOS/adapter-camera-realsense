"""RealSense list-devices command."""

from __future__ import annotations

import json
import sys

from forge_common import get_logger

logger = get_logger(__name__)


def _device_to_json(dev) -> dict[str, object]:
    return {
        "name": dev.name,
        "address": str(dev.index),
        "serial": dev.serial,
    }


def run_list_devices(*, json_output: bool = False) -> int:
    try:
        from .backend_realsense import list_realsense_devices
    except ImportError as e:
        logger.error("Failed to load pyrealsense2. Install pyrealsense2 and librealsense first.\n%s", e)
        return 1

    try:
        devices = list_realsense_devices()
    except Exception as e:
        logger.error("Failed to query RealSense devices: %s", e)
        return 1

    if json_output:
        json.dump({"devices": [_device_to_json(dev) for dev in devices]}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    if not devices:
        logger.info("No RealSense devices found.")
        logger.info("Check USB connection, librealsense packages, and udev rules.")
        return 0

    logger.info("Found %s RealSense device(s):", len(devices))
    logger.info("%-6s %-20s %-30s %-16s %-12s %s", "Index", "Serial", "Name", "Firmware", "Product", "USB")
    logger.info("%s", "-" * 100)
    for dev in devices:
        logger.info(
            "%-6s %-20s %-30s %-16s %-12s %s",
            dev.index,
            dev.serial,
            dev.name,
            dev.firmware_version,
            dev.product_line,
            dev.usb_type,
        )
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="List connected RealSense devices")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run_list_devices(json_output=args.json))

