"""RealSense SDK backend.

This file is the only place that should import `pyrealsense2`.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pyrealsense2 as rs
from forge_common import get_logger

from .backend import DeviceInfo, RealSenseFrame, depth_units_to_metres
from .config import FilterConfig, InfraredSideConfig, RealSenseConfig, StreamDataFlowConfig

logger = get_logger(__name__)


_FORMAT_MAP = {
    "bgr8": rs.format.bgr8,
    "bgra8": rs.format.bgra8,
    "rgb8": rs.format.rgb8,
    "rgba8": rs.format.rgba8,
    "yuyv": rs.format.yuyv,
    "raw16": rs.format.raw16,
    "mjpeg": rs.format.mjpeg,
    "jpeg": rs.format.mjpeg,
    "z16": rs.format.z16,
    "y8": rs.format.y8,
    "y16": rs.format.y16,
}

_OPTION_ALIASES = {
    "auto_exposure": "enable_auto_exposure",
    "auto_white_balance": "enable_auto_white_balance",
}

_FILTER_OPTION_ALIASES = {
    "min_m": "min_distance",
    "max_m": "max_distance",
    "magnitude": "filter_magnitude",
    "smooth_alpha": "filter_smooth_alpha",
    "smooth_delta": "filter_smooth_delta",
    "holes_fill": "holes_fill",
    "persistency_index": "holes_fill",
    "mode": "holes_fill",
    "rotation": "rotation",
    "sequence_id": "sequence_id",
}

_ADVANCED_MODE_PARAMETER_ALIASES = {
    ("depth_control", "ds_second_peak_threshold"): "param-secondpeakdelta",
    ("depth_control", "ds_neighbor_threshold"): "param-neighborthresh",
    ("depth_control", "ds_median_threshold"): "param-medianthreshold",
    ("depth_control", "estimate_median_increment"): "param-robbinsmonroincrement",
    ("depth_control", "estimate_median_decrement"): "param-robbinsmonrodecrement",
    ("depth_control", "score_minimum_threshold"): "param-minscorethresha",
    ("depth_control", "score_maximum_threshold"): "param-maxscorethreshb",
    ("depth_control", "ds_lr_threshold"): "param-leftrightthreshold",
    ("depth_control", "texture_count_threshold"): "param-texturecountthresh",
    ("depth_control", "texture_difference_threshold"): "param-texturedifferencethresh",
    ("rsm", "disparity_difference_threshold"): "param-rsmdiffthreshold",
    ("rsm", "slo_rau_difference_threshold"): "param-rsmrauslodiffthreshold",
    ("rsm", "remove_threshold"): "param-rsmremovethreshold",
    ("rau_support_vector_control", "min_west"): "param-rauminw",
    ("rau_support_vector_control", "min_east"): "param-raumine",
    ("rau_support_vector_control", "min_we_sum"): "param-rauminwesum",
    ("rau_support_vector_control", "min_north"): "param-rauminn",
    ("rau_support_vector_control", "min_south"): "param-raumins",
    ("rau_support_vector_control", "min_ns_sum"): "param-rauminnssum",
    ("rau_support_vector_control", "u_shrink"): "param-regionshrinku",
    ("rau_support_vector_control", "v_shrink"): "param-regionshrinkv",
    ("color_control", "disable_sad_color"): "param-disablesadcolor",
    ("color_control", "disable_rau_color"): "param-disableraucolor",
    ("color_control", "disable_slo_right_color"): "param-disableslorightcolor",
    ("color_control", "disable_slo_left_color"): "param-disablesloleftcolor",
    ("color_control", "disable_sad_normalize"): "param-disablesadnormalize",
    ("rau_color_thresholds_control", "diff_threshold_red"): "param-regioncolorthresholdr",
    ("rau_color_thresholds_control", "diff_threshold_green"): "param-regioncolorthresholdg",
    ("rau_color_thresholds_control", "diff_threshold_blue"): "param-regioncolorthresholdb",
    ("slo_color_thresholds_control", "diff_threshold_red"): "param-scanlineedgetaur",
    ("slo_color_thresholds_control", "diff_threshold_green"): "param-scanlineedgetaug",
    ("slo_color_thresholds_control", "diff_threshold_blue"): "param-scanlineedgetaub",
    ("slo_penalty_control", "k1_penalty"): "param-scanlinep1",
    ("slo_penalty_control", "k2_penalty"): "param-scanlinep2",
    ("slo_penalty_control", "k1_penalty_mod1"): "param-scanlinep1onediscon",
    ("slo_penalty_control", "k1_penalty_mod2"): "param-scanlinep1twodiscon",
    ("slo_penalty_control", "k2_penalty_mod1"): "param-scanlinep2onediscon",
    ("slo_penalty_control", "k2_penalty_mod2"): "param-scanlinep2twodiscon",
    ("hdad", "ignore_sad"): "ignoreSAD",
    ("hdad", "ad_lambda"): "param-lambdaad",
    ("hdad", "census_lambda"): "param-lambdacensus",
    ("depth_table", "depth_units"): "param-depthunits",
    ("depth_table", "depth_clamp_min"): "param-depthclampmin",
    ("depth_table", "depth_clamp_max"): "param-depthclampmax",
    ("depth_table", "disparity_mode"): "param-disparitymode",
    ("depth_table", "disparity_shift"): "param-disparityshift",
    ("ae_control", "mean_intensity_set_point"): "param-autoexposure-setpoint",
    ("census_enable_reg", "u_diameter"): "param-censusenablereg-udiameter",
    ("census_enable_reg", "v_diameter"): "param-censusenablereg-vdiameter",
    ("disparity_modulation", "a_factor"): "param-amplitude-factor",
}
_ADVANCED_MODE_PARAMETER_ALIASES.update(
    {("color_correction", f"color_correction_{idx}"): f"param-colorcorrection{idx}" for idx in range(1, 13)}
)
_ADVANCED_MODE_INVERTED_ALIASES = {
    ("rsm", "rsm_bypass"): "param-usersm",
}


def _rs_format(name: str) -> object:
    key = name.lower()
    if key not in _FORMAT_MAP:
        raise ValueError(f"Unsupported RealSense stream format: {name}")
    return _FORMAT_MAP[key]


def _sensor_name(sensor: object) -> str:
    try:
        return str(sensor.get_info(rs.camera_info.name))
    except RuntimeError:
        return "unknown"


def _advanced_key(name: object) -> str:
    return str(name).strip().lower().replace("-", "_").replace(" ", "_")


def _sensor_has_stream(sensor: object, stream_type: object) -> bool:
    for profile in sensor.get_stream_profiles():
        try:
            if profile.stream_type() == stream_type:
                return True
        except RuntimeError:
            continue
    return False


def _option_key(name: str) -> str:
    return name.split(".", 1)[1] if name.startswith("option.") else name


def _option_from_name(name: str) -> object | None:
    rs_name = _OPTION_ALIASES.get(_option_key(str(name)), _option_key(str(name)))
    return getattr(rs.option, rs_name, None)


def _set_option(sensor: object, option_name: str, value: float | bool | int | None) -> None:
    if value is None:
        return
    opt = _option_from_name(option_name)
    if opt is None:
        logger.warning("[realsense] unknown rs.option.%s, skip", option_name)
        return
    try:
        if sensor.supports(opt):
            sensor.set_option(opt, float(value))
            actual = sensor.get_option(opt)
            logger.info("[realsense] %s.%s: %s -> %g", _sensor_name(sensor), option_name, value, actual)
        else:
            logger.info("[realsense] %s does not support %s, skip", _sensor_name(sensor), option_name)
    except (RuntimeError, TypeError, ValueError) as e:
        logger.warning("[realsense] %s.%s=%s failed: %s", _sensor_name(sensor), option_name, value, e)


def _set_options(sensor: object, options: dict[str, Any]) -> None:
    for key, value in options.items():
        _set_option(sensor, key, value)


def _apply_orientation(arr: np.ndarray, *, mirror: bool, flip: bool, rotate: int) -> np.ndarray:
    if flip:
        arr = cv2.flip(arr, 0)
    if mirror:
        arr = cv2.flip(arr, 1)
    if rotate == 90:
        arr = cv2.rotate(arr, cv2.ROTATE_90_CLOCKWISE)
    elif rotate == 180:
        arr = cv2.rotate(arr, cv2.ROTATE_180)
    elif rotate == 270:
        arr = cv2.rotate(arr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return arr


def _apply_color_post_processing(arr: np.ndarray, options: dict[str, Any]) -> np.ndarray:
    decimation = options.get("decimation_filter", {}) or {}
    if decimation.get("enabled"):
        magnitude = int((decimation.get("options") or {}).get("filter_magnitude", 2))
        if magnitude > 1:
            arr = arr[::magnitude, ::magnitude]

    rotation = options.get("rotation_filter", {}) or {}
    if rotation.get("enabled"):
        rotate = int((rotation.get("options") or {}).get("rotation", 0))
        arr = _apply_orientation(arr, mirror=False, flip=False, rotate=rotate)
    return arr


class RealSenseBackend:
    """RealSense pipeline wrapper with background capture."""

    def __init__(self, config: RealSenseConfig) -> None:
        self._config = config
        self._pipeline: rs.pipeline | None = None
        self._profile: rs.pipeline_profile | None = None
        self._align: rs.align | None = None
        self._depth_scale = 0.001
        self._filters: list[tuple[str, object]] = []
        self._depth_to_disparity: object | None = None
        self._disparity_to_depth: object | None = None
        self._latest_frame: RealSenseFrame | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._first_frame_event = threading.Event()
        self._init_done = threading.Event()
        self._init_error: str | None = None
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="realsense-capture",
            daemon=True,
        )
        self._thread.start()

        if not self._init_done.wait(timeout=config.init_timeout_sec):
            self._stop_event.set()
            self.close()
            raise RuntimeError(
                f"RealSense initialization timed out ({config.init_timeout_sec}s). "
                "Check USB connection, librealsense packages, and udev rules."
            )
        if self._init_error:
            self.close()
            err = self._init_error
            if "errno=16" in err or "resource busy" in err.lower():
                raise RuntimeError(
                    f"RealSense initialization failed: {err}. "
                    "Another process may still hold the camera; try: "
                    "pkill -f 'realsense_camera' && pkill -f 'dist/realsense_camera'"
                ) from None
            raise RuntimeError(f"RealSense initialization failed: {err}")

    def capture_frame(self) -> RealSenseFrame:
        if not self._first_frame_event.wait(timeout=5.0):
            if not self._thread.is_alive():
                raise RuntimeError("RealSense capture thread exited before first frame.")
            raise RuntimeError("Timed out waiting for first RealSense frame.")
        with self._lock:
            frame = self._latest_frame
        if frame is None:
            raise RuntimeError("No RealSense frame available.")
        return frame

    def close(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5.0)

    def _wait_for_frames(self, timeout_ms: int, *, slice_ms: int = 500) -> object:
        """Poll wait_for_frames so close()/init timeout can interrupt promptly."""
        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        while not self._stop_event.is_set():
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                break
            try:
                if self._pipeline is None:
                    raise RuntimeError("RealSense pipeline is not started")
                return self._pipeline.wait_for_frames(min(slice_ms, remaining_ms))
            except RuntimeError as e:
                if self._is_disconnect_error(e):
                    raise
                continue
        if self._stop_event.is_set():
            raise RuntimeError("RealSense capture stopped while waiting for frames")
        raise RuntimeError(f"Frame didn't arrive within {timeout_ms}")

    def _capture_loop(self) -> None:
        try:
            if self._config.connect_delay_ms > 0:
                time.sleep(self._config.connect_delay_ms / 1000.0)

            self._pipeline = rs.pipeline()
            rs_config = self._build_rs_config()
            self._profile = self._pipeline.start(rs_config)
            self._apply_sensor_options()
            self._apply_advanced_mode_json()
            self._depth_scale = self._read_depth_scale()
            self._filters = self._build_filters()
            self._align = rs.align(rs.stream.color) if self._config.align_to == "color" else None

            # Option writes after start can stall streaming briefly.
            time.sleep(0.2)
            for i in range(max(0, self._config.prewarm_frames)):
                # First frames after reopen need a longer budget.
                self._wait_for_frames(10000 if i == 0 else 3000)

            self._init_done.set()

            while not self._stop_event.is_set():
                try:
                    frames = self._wait_for_frames(2000)
                except RuntimeError as e:
                    if self._stop_event.is_set():
                        break
                    if self._is_disconnect_error(e):
                        raise
                    continue
                if not frames:
                    continue
                if self._align is not None:
                    frames = self._align.process(frames)
                frame = self._convert_frameset(frames)
                with self._lock:
                    self._latest_frame = frame
                self._first_frame_event.set()
        except Exception as e:
            self._init_error = str(e)
            self._init_done.set()
            self._first_frame_event.set()
        finally:
            if self._pipeline is not None:
                try:
                    self._pipeline.stop()
                except RuntimeError:
                    pass

    def _build_rs_config(self) -> rs.config:
        cfg = self._config
        rs_config = rs.config()
        serial = cfg.device_serial or self._serial_by_index(cfg.device_index)
        if serial:
            rs_config.enable_device(serial)

        if cfg.color.data_flow.enabled:
            self._enable_video_stream(rs_config, rs.stream.color, cfg.color.data_flow)
        if cfg.depth.data_flow.enabled:
            self._enable_video_stream(rs_config, rs.stream.depth, cfg.depth.data_flow)
        if cfg.infrared.left.enabled:
            self._enable_ir_stream(rs_config, cfg.infrared.left)
        if cfg.infrared.right.enabled:
            self._enable_ir_stream(rs_config, cfg.infrared.right)
        return rs_config

    @staticmethod
    def _enable_video_stream(rs_config: rs.config, stream_type: object, stream: StreamDataFlowConfig) -> None:
        rs_config.enable_stream(
            stream_type,
            stream.width,
            stream.height,
            _rs_format(stream.format),
            stream.fps,
        )

    @staticmethod
    def _enable_ir_stream(rs_config: rs.config, stream: InfraredSideConfig) -> None:
        rs_config.enable_stream(
            rs.stream.infrared,
            stream.stream_index,
            stream.width,
            stream.height,
            _rs_format(stream.format),
            stream.fps,
        )

    @staticmethod
    def _serial_by_index(index: int) -> str | None:
        ctx = rs.context()
        devices = list(ctx.query_devices())
        if not devices:
            raise RuntimeError("No RealSense device found.")
        if index < 0 or index >= len(devices):
            raise RuntimeError(f"RealSense device_index {index} out of range, found {len(devices)} device(s).")
        device = devices[index]
        if device.supports(rs.camera_info.serial_number):
            return str(device.get_info(rs.camera_info.serial_number))
        return None

    def _apply_advanced_mode_json(self) -> None:
        updates = self._advanced_mode_parameter_updates()
        if not self._config.advanced_mode_json and not updates:
            return
        if self._profile is None:
            return
        payload: dict[str, Any] | None = None
        path: Path | None = None
        if self._config.advanced_mode_json:
            path = Path(self._config.advanced_mode_json)
            payload = json.loads(path.read_text(encoding="utf-8"))
        device = self._profile.get_device()
        try:
            advanced = rs.rs400_advanced_mode(device)
            if not advanced.is_enabled():
                advanced.toggle_advanced_mode(True)
                time.sleep(1.0)
            if payload is None:
                payload = json.loads(advanced.serialize_json())
            parameters = payload.setdefault("parameters", {})
            if not isinstance(parameters, dict):
                raise ValueError("advanced mode JSON parameters must be a mapping")
            parameters.update(updates)
            advanced.load_json(json.dumps(payload))
            source = str(path) if path is not None else "current device settings"
            logger.info("[realsense] loaded advanced mode settings from %s; overrides=%d", source, len(updates))
        except Exception as e:
            logger.warning("[realsense] advanced mode settings failed: %s", e)

    def _advanced_mode_parameter_updates(self) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        for group_name, raw_group in self._config.depth.advanced_controls.items():
            if raw_group is None:
                continue
            if not isinstance(raw_group, dict):
                logger.warning("[realsense] advanced_controls.%s must be a mapping, skip", group_name)
                continue
            group_key = _advanced_key(group_name)
            for field_name, value in raw_group.items():
                if value is None:
                    continue
                if isinstance(field_name, str) and (
                    field_name.startswith("param-")
                    or field_name.startswith("aux-param-")
                    or field_name == "ignoreSAD"
                ):
                    updates[field_name] = value
                    continue
                field_key = _advanced_key(field_name)
                alias_key = (group_key, field_key)
                if alias_key in _ADVANCED_MODE_INVERTED_ALIASES:
                    updates[_ADVANCED_MODE_INVERTED_ALIASES[alias_key]] = 0 if bool(value) else 1
                    continue
                json_key = _ADVANCED_MODE_PARAMETER_ALIASES.get(alias_key)
                if json_key is None:
                    logger.warning("[realsense] unknown advanced control %s.%s, skip", group_name, field_name)
                    continue
                updates[json_key] = value
        return updates

    def _apply_sensor_options(self) -> None:
        if self._profile is None:
            return
        cfg = self._config
        device = self._profile.get_device()
        for sensor in device.sensors:
            _set_options(sensor, cfg.options)

            if cfg.color.data_flow.enabled and _sensor_has_stream(sensor, rs.stream.color):
                _set_options(sensor, self._color_options())

            # Stereo Module exposes depth + IR on one sensor. Apply depth controls
            # once here; IR-only option maps are for non-stereo layouts.
            if cfg.depth.data_flow.enabled and _sensor_has_stream(sensor, rs.stream.depth):
                _set_options(sensor, self._depth_options())
            elif (
                (cfg.infrared.left.enabled or cfg.infrared.right.enabled)
                and _sensor_has_stream(sensor, rs.stream.infrared)
            ):
                options = dict(cfg.infrared.options)
                if cfg.infrared.left.enabled:
                    options.update(cfg.infrared.left.options)
                if cfg.infrared.right.enabled:
                    options.update(cfg.infrared.right.options)
                _set_options(sensor, options)

    def _color_options(self) -> dict[str, Any]:
        c = self._config.color.control
        options: dict[str, Any] = {
            "brightness": c.brightness,
            "contrast": c.contrast,
            "saturation": c.saturation,
            "sharpness": c.sharpness,
            "gamma": c.gamma,
            "hue": c.hue,
            "backlight_compensation": c.backlight_compensation,
            "power_line_frequency": c.power_line_frequency,
            "auto_exposure_priority": c.auto_exposure_priority,
            "global_time_enabled": c.global_time_enabled,
        }
        if c.auto_exposure:
            options.update({"exposure": c.exposure, "gain": c.gain, "auto_exposure": c.auto_exposure})
        else:
            options.update({"auto_exposure": c.auto_exposure, "exposure": c.exposure, "gain": c.gain})
        if c.auto_white_balance:
            options.update({"white_balance": c.white_balance, "auto_white_balance": c.auto_white_balance})
        else:
            options.update({"auto_white_balance": c.auto_white_balance, "white_balance": c.white_balance})
        options.update(self._config.color.options)
        return options

    def _depth_options(self) -> dict[str, Any]:
        d = self._config.depth.control
        options: dict[str, Any] = {
            "visual_preset": d.visual_preset,
            "depth_auto_exposure_mode": d.depth_auto_exposure_mode,
            "laser_power": d.laser_power,
            "emitter_enabled": d.emitter_enabled,
            "emitter_on_off": d.emitter_on_off,
            "depth_units": d.depth_units,
            "inter_cam_sync_mode": d.inter_cam_sync_mode,
        }
        if d.auto_exposure:
            options.update({"exposure": d.exposure, "gain": d.gain, "auto_exposure": d.auto_exposure})
        else:
            options.update({"auto_exposure": d.auto_exposure, "exposure": d.exposure, "gain": d.gain})
        options.update(
            {
                key: value
                for key, value in self._config.depth.advanced_controls.items()
                if not isinstance(value, dict)
            }
        )
        options.update(self._config.depth.options)
        return options

    def _read_depth_scale(self) -> float:
        if self._profile is None or not self._config.depth.data_flow.enabled:
            return 0.001
        try:
            depth_sensor = self._profile.get_device().first_depth_sensor()
            scale = float(depth_sensor.get_depth_scale())
            logger.info("[realsense] depth_scale=%g meters/unit", scale)
            return scale
        except RuntimeError as e:
            logger.warning("[realsense] read depth_scale failed, fallback 0.001: %s", e)
            return 0.001

    def _build_filters(self) -> list[tuple[str, object]]:
        pp = self._config.post_processing
        filters: list[tuple[str, object]] = []
        for name, spec, factory in (
            ("decimation_filter", pp.decimation_filter, rs.decimation_filter),
            ("threshold_filter", pp.threshold_filter, rs.threshold_filter),
            ("rotation_filter", pp.rotation_filter, rs.rotation_filter),
            ("hdr_merge", pp.hdr_merge, rs.hdr_merge),
            ("sequence_id_filter", pp.sequence_id_filter, rs.sequence_id_filter),
            ("spatial_filter", pp.spatial_filter, rs.spatial_filter),
            ("temporal_filter", pp.temporal_filter, rs.temporal_filter),
            ("hole_filling_filter", pp.hole_filling_filter, rs.hole_filling_filter),
        ):
            if not spec.enabled:
                continue
            try:
                filt = factory()
                self._apply_filter_options(filt, spec)
                filters.append((name, filt))
            except RuntimeError as e:
                logger.warning("[realsense] filter %s setup failed: %s", name, e)
        if pp.depth_to_disparity.enabled or pp.spatial_filter.enabled or pp.temporal_filter.enabled:
            try:
                self._depth_to_disparity = rs.disparity_transform(True)
            except RuntimeError as e:
                logger.warning("[realsense] disparity transform setup failed: %s", e)
        if pp.disparity_to_depth.enabled or self._depth_to_disparity is not None:
            try:
                self._disparity_to_depth = rs.disparity_transform(False)
            except RuntimeError as e:
                logger.warning("[realsense] disparity-to-depth setup failed: %s", e)
        return filters

    @staticmethod
    def _apply_filter_options(filt: object, spec: FilterConfig) -> None:
        try:
            supported_options = {int(opt) for opt in filt.get_supported_options()}
        except (AttributeError, RuntimeError, TypeError):
            supported_options = set()

        for key, value in spec.options.items():
            if value is None:
                continue
            rs_name = _FILTER_OPTION_ALIASES.get(_option_key(str(key)), _option_key(str(key)))
            opt = getattr(rs.option, rs_name, None)
            if opt is None:
                logger.warning("[realsense] unknown filter option %s, skip", key)
                continue
            try:
                if supported_options and int(opt) not in supported_options:
                    continue
                if supported_options or filt.supports(opt):
                    filt.set_option(opt, float(value))
            except (RuntimeError, TypeError, ValueError) as e:
                logger.warning("[realsense] filter option %s=%s failed: %s", key, value, e)

    def _process_depth_filter(self, frame: object, filter_name: str) -> object:
        for name, filt in self._filters:
            if name != filter_name:
                continue
            processed = filt.process(frame)
            if processed:
                return processed
        return frame

    def _convert_frameset(self, frames: object) -> RealSenseFrame:
        color = self._extract_color(frames)
        depth = self._extract_depth(frames)
        ir_left, ir_right = self._extract_ir(frames)
        timestamp_ms = 0
        try:
            ref = frames.get_color_frame() or frames.get_depth_frame()
            if ref:
                timestamp_ms = int(ref.get_timestamp())
        except RuntimeError:
            pass
        return RealSenseFrame(
            color=color,
            depth=depth,
            ir_left=ir_left,
            ir_right=ir_right,
            timestamp_ms=timestamp_ms,
        )

    def _extract_color(self, frames: object) -> np.ndarray | None:
        if not self._config.color.data_flow.enabled:
            return None
        frame = frames.get_color_frame()
        if not frame:
            return None
        arr = np.asanyarray(frame.get_data())
        fmt = frame.get_profile().format()
        if fmt == rs.format.bgr8:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        elif fmt == rs.format.bgra8:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)
        elif fmt == rs.format.rgb8:
            arr = np.array(arr, copy=False)
        elif fmt == rs.format.rgba8:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
        elif fmt == rs.format.yuyv:
            bgr = cv2.cvtColor(arr, cv2.COLOR_YUV2BGR_YUYV)
            arr = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        elif fmt == rs.format.raw16:
            gray = cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            arr = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
        elif fmt == rs.format.mjpeg:
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if bgr is None:
                return None
            arr = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        else:
            return None
        arr = _apply_color_post_processing(arr, self._config.color.post_processing)
        c = self._config.color.control
        return _apply_orientation(arr, mirror=c.mirror, flip=c.flip, rotate=c.rotate)

    def _extract_depth(self, frames: object) -> np.ndarray | None:
        if not self._config.depth.data_flow.enabled:
            return None
        frame = frames.get_depth_frame()
        if not frame:
            return None
        processed_frame = frame

        for name in (
            "decimation_filter",
            "threshold_filter",
            "rotation_filter",
            "hdr_merge",
            "sequence_id_filter",
        ):
            processed_frame = self._process_depth_filter(processed_frame, name)

        if self._depth_to_disparity is not None:
            converted = self._depth_to_disparity.process(processed_frame)
            if converted:
                processed_frame = converted

        for name in ("spatial_filter", "temporal_filter"):
            processed_frame = self._process_depth_filter(processed_frame, name)

        if self._disparity_to_depth is not None and not processed_frame.is_depth_frame():
            converted = self._disparity_to_depth.process(processed_frame)
            if converted:
                processed_frame = converted

        processed_frame = self._process_depth_filter(processed_frame, "hole_filling_filter")
        frame = processed_frame.as_depth_frame()
        if not frame:
            return None
        raw = np.asanyarray(frame.get_data())
        d = self._config.depth.control
        depth_m = depth_units_to_metres(
            raw,
            depth_scale=self._depth_scale,
            min_mm=d.min_mm,
            max_mm=d.max_mm,
        )
        return _apply_orientation(depth_m, mirror=d.mirror, flip=d.flip, rotate=d.rotate)

    def _extract_ir(self, frames: object) -> tuple[np.ndarray | None, np.ndarray | None]:
        left: np.ndarray | None = None
        right: np.ndarray | None = None
        cfg = self._config.infrared
        if not cfg.left.enabled and not cfg.right.enabled:
            return left, right
        try:
            iterator = iter(frames)
        except TypeError:
            return left, right
        for frame in iterator:
            try:
                profile = frame.get_profile()
                if profile.stream_type() != rs.stream.infrared:
                    continue
                arr = np.asanyarray(frame.get_data())
                index = int(profile.stream_index())
                if index == cfg.left.stream_index and cfg.left.enabled:
                    left = _apply_orientation(
                        arr,
                        mirror=cfg.left.mirror,
                        flip=cfg.left.flip,
                        rotate=cfg.left.rotate,
                    )
                elif index == cfg.right.stream_index and cfg.right.enabled:
                    right = _apply_orientation(
                        arr,
                        mirror=cfg.right.mirror,
                        flip=cfg.right.flip,
                        rotate=cfg.right.rotate,
                    )
            except RuntimeError:
                continue
        return left, right

    @staticmethod
    def _is_disconnect_error(e: Exception) -> bool:
        msg = str(e).lower()
        return any(
            kw in msg
            for kw in ("no such device", "disconnected", "device not found", "i/o error")
        )


def hardware_reset_devices() -> None:
    """Issue a firmware-level reset for all connected RealSense devices.

    Rapid stop/start on some D400 units leaves the USB streaming endpoint wedged
    until a hardware reset; callers should wait a few seconds afterwards.
    """
    ctx = rs.context()
    devices = list(ctx.query_devices())
    if not devices:
        logger.warning("[realsense] hardware_reset: no devices found")
        return
    for device in devices:
        serial = ""
        try:
            if device.supports(rs.camera_info.serial_number):
                serial = str(device.get_info(rs.camera_info.serial_number))
            device.hardware_reset()
            logger.warning("[realsense] hardware_reset issued for %s", serial or "?")
        except RuntimeError as e:
            logger.warning("[realsense] hardware_reset failed for %s: %s", serial or "?", e)
    time.sleep(4.0)


def list_realsense_devices() -> list[DeviceInfo]:
    """List connected RealSense devices."""
    ctx = rs.context()
    devices = list(ctx.query_devices())
    result: list[DeviceInfo] = []
    for index, device in enumerate(devices):
        def _info(info: object) -> str:
            try:
                if device.supports(info):
                    return str(device.get_info(info))
            except RuntimeError:
                return ""
            return ""

        result.append(
            DeviceInfo(
                index=index,
                serial=_info(rs.camera_info.serial_number),
                name=_info(rs.camera_info.name),
                firmware_version=_info(rs.camera_info.firmware_version),
                product_line=_info(rs.camera_info.product_line),
                usb_type=_info(rs.camera_info.usb_type_descriptor),
            )
        )
    return result


__all__ = ["RealSenseBackend", "list_realsense_devices"]

