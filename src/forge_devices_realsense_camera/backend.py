"""RealSense capture backend abstraction.

This module must stay SDK-free. Concrete RealSense SDK code belongs in
`backend_realsense.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import numpy as np

if TYPE_CHECKING:
    from .config import RealSenseConfig


@dataclass
class RealSenseFrame:
    """One capture cycle of RealSense image streams."""

    color: np.ndarray | None
    depth: np.ndarray | None
    ir_left: np.ndarray | None
    ir_right: np.ndarray | None
    timestamp_ms: int = 0
    capture_timestamp_ns: int | None = None


@dataclass
class DeviceInfo:
    """Connected RealSense device info for list-devices."""

    index: int
    serial: str
    name: str
    firmware_version: str = ""
    product_line: str = ""
    usb_type: str = ""


def depth_units_to_metres(
    raw: np.ndarray,
    *,
    depth_scale: float,
    min_mm: int,
    max_mm: int,
) -> np.ndarray:
    """Convert vendor depth units to float32 metres and clear out-of-range pixels."""
    depth_m = raw.astype(np.float32) * np.float32(depth_scale)
    valid = depth_m > 0
    clip = valid & (
        (depth_m < np.float32(min_mm / 1000.0))
        | (depth_m > np.float32(max_mm / 1000.0))
    )
    if np.any(clip):
        depth_m = depth_m.copy()
        depth_m[clip] = 0.0
    return depth_m


@runtime_checkable
class CaptureBackend(Protocol):
    """Common interface implemented by RealSense capture backends."""

    def capture_frame(self) -> RealSenseFrame:
        """Return the latest captured frame."""
        ...

    def close(self) -> None:
        """Release camera resources."""
        ...


def create_backend(config: RealSenseConfig) -> CaptureBackend:
    """Create the concrete RealSense backend.

    On some D400 devices, a previous pipeline stop can leave USB streaming wedged
    so the next start never delivers frames. Retry once after a hardware reset.
    """
    from forge_common import get_logger

    from .backend_realsense import RealSenseBackend, hardware_reset_devices

    logger = get_logger(__name__)
    try:
        return RealSenseBackend(config)
    except RuntimeError as e:
        msg = str(e).lower()
        retryable = (
            "frame didn't arrive" in msg
            or "timed out" in msg
            or "errno=16" in msg
            or "resource busy" in msg
        )
        if not retryable:
            raise
        logger.warning(
            "[realsense] init failed (%s); hardware_reset and retry once",
            e,
        )
        hardware_reset_devices()
        return RealSenseBackend(config)

