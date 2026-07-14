"""Compatibility entrypoint for the former device probe tool.

Detailed profile and option inspection belongs in Intel's realsense-viewer.
This module remains importable after the src-layout migration.
"""

from __future__ import annotations

from forge_common import get_logger

from .list_devices import run_list_devices

logger = get_logger(__name__)


def main() -> int:
    logger.info(
        "Detailed profile probing moved to realsense-viewer; "
        "listing devices through the SDK backend."
    )
    return run_list_devices()


if __name__ == "__main__":
    raise SystemExit(main())
