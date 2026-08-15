"""RealSense snapshot command scaffold."""

from __future__ import annotations

import sys
from dataclasses import replace
from importlib import resources
from pathlib import Path

import cv2
import numpy as np
from forge_common import get_logger
from forge_msgs import CompressedImage

from .backend import RealSenseFrame, create_backend
from .config import RealSenseConfig

logger = get_logger(__name__)

SNAPSHOT_DISCARD_FRAMES = 2
SNAPSHOT_MAX_EMPTY_RETRIES = 24
_DEFAULT_CONFIG_PATH = Path("config/sensor.example.yaml")


def _default_config_path() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root is not None:
        return Path(frozen_root) / _DEFAULT_CONFIG_PATH

    source_config = Path(__file__).resolve().parents[2] / _DEFAULT_CONFIG_PATH
    if source_config.is_file():
        return source_config

    packaged = resources.files("forge_devices_realsense_camera").joinpath(
        "resources", "sensor.example.yaml"
    )
    return Path(str(packaged))


def _is_usable_color_frame(rgb: np.ndarray | None) -> bool:
    """Reject missing/malformed images without treating darkness as corruption."""
    return rgb is not None and rgb.ndim == 3 and rgb.size > 0


def _write_color_jpeg(rgb: np.ndarray, out_path: Path, quality: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    q = max(1, min(100, int(quality)))
    image = CompressedImage.from_numpy(rgb, format="jpeg", quality=q)
    out_path.write_bytes(image.data)


def _write_png(arr: np.ndarray, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", arr)
    if not ok:
        raise RuntimeError(f"PNG encode failed: {out_path}")
    out_path.write_bytes(buf.tobytes())


def resolve_snapshot_config(
    *,
    yaml_path: str | None,
    device_index: int | None,
    device_serial: str | None,
) -> RealSenseConfig:
    config_path = Path(yaml_path).expanduser() if yaml_path else _default_config_path()
    config = RealSenseConfig.from_yaml_path(config_path)
    if device_index is not None:
        if device_index < 0:
            raise ValueError("device_index must be >= 0")
        config.device_index = device_index
        # An explicit CLI index selects by index, not by a serial inherited from YAML.
        config.device_serial = None
    if device_serial:
        config.device_serial = device_serial
    return config


def run_snapshot(
    config: RealSenseConfig,
    output_path: str,
    *,
    jpeg_quality: int | None,
    all_streams: bool,
) -> int:
    cfg = config
    if jpeg_quality is not None:
        jq = max(1, min(100, int(jpeg_quality)))
        cfg = replace(cfg, color=replace(cfg.color, jpeg_quality=jq))

    out_arg = Path(output_path).expanduser().resolve()
    backend = None
    result = 1
    try:
        backend = create_backend(cfg)
        last_sequence = 0
        for _ in range(SNAPSHOT_DISCARD_FRAMES):
            discarded = backend.capture_frame(after_sequence=last_sequence)
            last_sequence = discarded.capture_sequence

        frame: RealSenseFrame | None = None
        for attempt in range(SNAPSHOT_MAX_EMPTY_RETRIES + 1):
            candidate = backend.capture_frame(after_sequence=last_sequence)
            last_sequence = candidate.capture_sequence
            if _is_usable_color_frame(candidate.color):
                frame = candidate
                break
            if attempt > 0 and attempt % 8 == 0:
                logger.warning("snapshot: color frame is still empty, keep trying")

        if frame is None or frame.color is None:
            logger.error("snapshot: no usable color frame after retries")
        elif not all_streams:
            _write_color_jpeg(frame.color, out_arg, cfg.color.jpeg_quality)
            logger.info("snapshot: wrote %s", out_arg)
            result = 0
        else:
            parent = out_arg.parent
            stem = out_arg.stem if out_arg.suffix else out_arg.name
            color_path = parent / f"{stem}_color.jpg"
            depth_path = parent / f"{stem}_depth_m.npy"
            ir_left_path = parent / f"{stem}_ir_left.png"
            ir_right_path = parent / f"{stem}_ir_right.png"

            written = []
            _write_color_jpeg(frame.color, color_path, cfg.color.jpeg_quality)
            written.append(str(color_path))

            if cfg.depth.data_flow.enabled and frame.depth is not None:
                np.save(depth_path, frame.depth.astype(np.float32, copy=False))
                written.append(str(depth_path))
            elif cfg.depth.data_flow.enabled:
                logger.warning("snapshot: depth enabled but frame is empty")

            if cfg.infrared.left.enabled and frame.ir_left is not None:
                _write_png(frame.ir_left, ir_left_path)
                written.append(str(ir_left_path))
            elif cfg.infrared.left.enabled:
                logger.warning("snapshot: ir_left enabled but frame is empty")

            if cfg.infrared.right.enabled and frame.ir_right is not None:
                _write_png(frame.ir_right, ir_right_path)
                written.append(str(ir_right_path))
            elif cfg.infrared.right.enabled:
                logger.warning("snapshot: ir_right enabled but frame is empty")

            logger.info("snapshot: wrote\n  %s", "\n  ".join(written))
            result = 0
    except Exception as e:
        logger.error("snapshot failed: %s", e)
        result = 1
    finally:
        try:
            if backend is not None:
                backend.close()
        except Exception as e:
            logger.error("snapshot close failed: %s", e)
            result = 1
    return result

