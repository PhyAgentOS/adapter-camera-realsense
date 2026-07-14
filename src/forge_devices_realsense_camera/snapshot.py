"""RealSense snapshot command scaffold."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
from forge_common import get_logger
from forge_msgs import CompressedImage

from .backend import RealSenseFrame, create_backend
from .config import RealSenseConfig

logger = get_logger(__name__)

SNAPSHOT_DISCARD_FRAMES = 2
SNAPSHOT_MAX_DARK_SKIPS = 24
_MIN_CONTENT_MEAN = 10.0
_DEFAULT_CONFIG_PATH = Path("config/sensor.example.yaml")


def _default_config_path() -> Path:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base_dir / _DEFAULT_CONFIG_PATH


def _rgb_has_visible_content(rgb: np.ndarray) -> bool:
    if rgb is None or rgb.size == 0 or rgb.ndim != 3:
        return False
    h, w = rgb.shape[:2]
    if h < 2 or w < 2:
        return float(np.mean(rgb)) > _MIN_CONTENT_MEAN
    small = cv2.resize(rgb, (48, 27), interpolation=cv2.INTER_AREA)
    return float(small.mean()) > _MIN_CONTENT_MEAN


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
        config.device_index = device_index
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
    backend = create_backend(cfg)
    try:
        for _ in range(SNAPSHOT_DISCARD_FRAMES):
            _ = backend.capture_frame()

        frame: RealSenseFrame | None = None
        for attempt in range(SNAPSHOT_MAX_DARK_SKIPS + 1):
            f = backend.capture_frame()
            if f.color is not None and _rgb_has_visible_content(f.color):
                frame = f
                break
            if attempt > 0 and attempt % 8 == 0:
                logger.warning("snapshot: frame is still dark/empty, keep trying")

        if frame is None or frame.color is None:
            logger.error("snapshot: no valid color frame after retries")
            return 1

        if not all_streams:
            _write_color_jpeg(frame.color, out_arg, cfg.color.jpeg_quality)
            logger.info("snapshot: wrote %s", out_arg)
            return 0

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
        return 0
    except Exception as e:
        logger.error("snapshot failed: %s", e)
        return 1
    finally:
        backend.close()

