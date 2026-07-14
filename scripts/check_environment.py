#!/usr/bin/env python3
"""Check software prerequisites without opening camera hardware."""

from __future__ import annotations

import importlib.util
import platform
import shutil
import sys


def main() -> int:
    checks = {
        "python>=3.11": sys.version_info >= (3, 11),
        "linux": platform.system() == "Linux",
        "pyrealsense2": importlib.util.find_spec("pyrealsense2") is not None,
        "realsense-viewer": shutil.which("realsense-viewer") is not None,
        "rs-enumerate-devices": shutil.which("rs-enumerate-devices") is not None,
    }
    for name, ok in checks.items():
        print(f"{'OK' if ok else 'MISSING':7} {name}")
    required = ("python>=3.11", "linux", "pyrealsense2")
    return 0 if all(checks[name] for name in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
