"""RealSense capture backend abstraction.

This module must stay SDK-free. Concrete RealSense SDK code belongs in
`backend_realsense.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import numpy as np

if TYPE_CHECKING:
    from .config import RealSenseConfig


@dataclass(frozen=True)
class RealSensePointCloud:
    """SDK-independent, immutable organized point-cloud columns."""

    width: int
    height: int
    is_dense: bool
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    rgb: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None


@dataclass
class RealSenseFrame:
    """One capture cycle of RealSense image and derived point-cloud streams."""

    color: np.ndarray | None
    depth: np.ndarray | None
    ir_left: np.ndarray | None
    ir_right: np.ndarray | None
    timestamp_ms: int = 0
    capture_timestamp_ns: int | None = None
    capture_sequence: int = 0
    point_cloud: RealSensePointCloud | None = None


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

    def capture_frame(
        self,
        *,
        after_sequence: int | None = None,
        timeout_sec: float = 5.0,
    ) -> RealSenseFrame:
        """Return a frame, optionally waiting for one newer than ``after_sequence``."""
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

    from .backend_realsense import (
        RealSenseBackend,
        hardware_reset_device,
        resolve_device_serial,
    )

    logger = get_logger(__name__)
    resolved_serial = resolve_device_serial(config)
    pinned_config = replace(config, device_serial=resolved_serial)
    try:
        return RealSenseBackend(pinned_config)
    except RuntimeError as e:
        msg = str(e).lower()
        retryable_hint = getattr(e, "retryable", None)
        retryable = retryable_hint if retryable_hint is not None else (
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
        hardware_reset_device(resolved_serial)
        return RealSenseBackend(pinned_config)

