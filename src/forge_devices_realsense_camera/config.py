"""RealSense node configuration."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


@dataclass
class StreamDataFlowConfig:
    enabled: bool = True
    width: int = 640
    height: int = 480
    fps: int = 30
    format: str = "bgr8"


@dataclass
class ColorControlConfig:
    auto_exposure: bool | None = None
    exposure: float | None = None
    gain: float | None = None
    auto_white_balance: bool | None = None
    white_balance: float | None = None
    brightness: float | None = None
    contrast: float | None = None
    saturation: float | None = None
    sharpness: float | None = None
    gamma: float | None = None
    hue: float | None = None
    backlight_compensation: float | None = None
    power_line_frequency: float | None = None
    auto_exposure_priority: float | None = None
    global_time_enabled: float | None = None
    mirror: bool = False
    flip: bool = False
    rotate: int = 0


@dataclass
class ColorConfig:
    data_flow: StreamDataFlowConfig = field(default_factory=StreamDataFlowConfig)
    control: ColorControlConfig = field(default_factory=ColorControlConfig)
    options: dict[str, Any] = field(default_factory=dict)
    post_processing: dict[str, Any] = field(default_factory=dict)
    jpeg_quality: int = 85


@dataclass
class DepthControlConfig:
    visual_preset: float | None = None
    auto_exposure: bool | None = None
    depth_auto_exposure_mode: float | None = None
    exposure: float | None = None
    gain: float | None = None
    laser_power: float | None = None
    emitter_enabled: float | None = None
    emitter_on_off: float | None = None
    depth_units: float | None = None
    inter_cam_sync_mode: float | None = None
    min_mm: int = 100
    max_mm: int = 10000
    mirror: bool = False
    flip: bool = False
    rotate: int = 0


@dataclass
class DepthConfig:
    data_flow: StreamDataFlowConfig = field(
        default_factory=lambda: StreamDataFlowConfig(format="z16")
    )
    control: DepthControlConfig = field(default_factory=DepthControlConfig)
    options: dict[str, Any] = field(default_factory=dict)
    advanced_controls: dict[str, Any] = field(default_factory=dict)


@dataclass
class InfraredSideConfig:
    enabled: bool = False
    stream_index: int = 1
    width: int = 640
    height: int = 480
    fps: int = 30
    format: str = "y8"
    mirror: bool = False
    flip: bool = False
    rotate: int = 0
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class InfraredConfig:
    left: InfraredSideConfig = field(
        default_factory=lambda: InfraredSideConfig(enabled=True, stream_index=1)
    )
    right: InfraredSideConfig = field(
        default_factory=lambda: InfraredSideConfig(enabled=False, stream_index=2)
    )
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class FilterConfig:
    enabled: bool = False
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class PostProcessingConfig:
    threshold_filter: FilterConfig = field(default_factory=FilterConfig)
    decimation_filter: FilterConfig = field(default_factory=FilterConfig)
    rotation_filter: FilterConfig = field(default_factory=FilterConfig)
    hdr_merge: FilterConfig = field(default_factory=FilterConfig)
    sequence_id_filter: FilterConfig = field(default_factory=FilterConfig)
    depth_to_disparity: FilterConfig = field(default_factory=FilterConfig)
    spatial_filter: FilterConfig = field(default_factory=FilterConfig)
    temporal_filter: FilterConfig = field(default_factory=FilterConfig)
    hole_filling_filter: FilterConfig = field(default_factory=FilterConfig)
    disparity_to_depth: FilterConfig = field(default_factory=FilterConfig)


@dataclass
class PointCloudConfig:
    enabled: bool = False
    colorize: bool = True
    frame_id: str | None = None


@dataclass
class RealSenseConfig:
    device_serial: str | None = None
    device_index: int = 0
    options: dict[str, Any] = field(default_factory=dict)
    connect_delay_ms: int = 0
    init_timeout_sec: float = 15.0
    prewarm_frames: int = 0
    align_to: Literal["disable", "color"] = "color"
    advanced_mode_json: str | None = None
    output_color: str = "image/color"
    output_depth: str = "image/depth"
    output_ir_left: str = "image/ir_left"
    output_ir_right: str = "image/ir_right"
    color: ColorConfig = field(default_factory=ColorConfig)
    depth: DepthConfig = field(default_factory=DepthConfig)
    infrared: InfraredConfig = field(default_factory=InfraredConfig)
    post_processing: PostProcessingConfig = field(default_factory=PostProcessingConfig)
    output_point_cloud: str = "point_cloud"
    point_cloud: PointCloudConfig = field(default_factory=PointCloudConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RealSenseConfig:
        """Build config from YAML data."""

        if not isinstance(data, dict):
            raise ValueError("RealSense config must be a mapping")

        def _bool(value: Any, *, key: str) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, int) and value in (0, 1):
                return bool(value)
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in ("true", "1"):
                    return True
                if normalized in ("false", "0"):
                    return False
            raise ValueError(f"{key} must be a boolean (true/false or 1/0), got {value!r}")

        def _int(value: Any, *, key: str) -> int:
            if isinstance(value, bool):
                raise ValueError(f"{key} must be an integer, got {value!r}")
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                normalized = value.strip()
                digits = normalized[1:] if normalized[:1] in ("+", "-") else normalized
                if digits.isdigit():
                    return int(normalized)
            raise ValueError(f"{key} must be an integer, got {value!r}")

        def _float(value: Any, *, key: str) -> float:
            if isinstance(value, bool):
                raise ValueError(f"{key} must be a number, got {value!r}")
            try:
                result = float(value)
            except (TypeError, ValueError) as e:
                raise ValueError(f"{key} must be a number, got {value!r}") from e
            if not math.isfinite(result):
                raise ValueError(f"{key} must be finite, got {value!r}")
            return result

        def _opt_float(value: Any, *, key: str) -> float | None:
            return None if value is None else _float(value, key=key)

        def _opt_bool(raw: dict[str, Any], key: str, *, prefix: str) -> bool | None:
            return (
                None
                if key not in raw or raw[key] is None
                else _bool(raw[key], key=f"{prefix}.{key}")
            )

        def _rotate(value: Any, *, key: str) -> int:
            rotate = _int(value, key=key)
            if rotate not in (0, 90, 180, 270):
                raise ValueError(f"{key} must be one of 0/90/180/270, got {rotate}")
            return rotate

        def _stream(
            raw: dict[str, Any],
            *,
            field_name: str,
            default_format: str,
            default_enabled: bool = True,
        ) -> StreamDataFlowConfig:
            stream_name = field_name
            raw_format = raw.get("format", default_format)
            if not isinstance(raw_format, str):
                raise ValueError(f"{stream_name}.format must be a string, got {raw_format!r}")
            return StreamDataFlowConfig(
                enabled=_bool(raw.get("enabled", default_enabled), key=f"{stream_name}.enabled"),
                width=_int(raw.get("width", 640), key=f"{stream_name}.width"),
                height=_int(raw.get("height", 480), key=f"{stream_name}.height"),
                fps=_int(raw.get("fps", 30), key=f"{stream_name}.fps"),
                format=raw_format.strip().lower(),
            )

        def _validate_stream(name: str, stream: StreamDataFlowConfig) -> None:
            if stream.width <= 0 or stream.height <= 0:
                raise ValueError(f"{name}.width/height must be > 0")
            if stream.fps <= 0:
                raise ValueError(f"{name}.fps must be > 0")

        def _dict(raw: Any, *, key: str) -> dict[str, Any]:
            if raw is None:
                return {}
            if not isinstance(raw, dict):
                raise ValueError(f"{key} must be a mapping")
            return dict(raw)

        color_raw = _dict(data.get("color"), key="color")
        color_df = _dict(color_raw.get("data_flow"), key="color.data_flow")
        color_ctrl = _dict(
            color_raw.get("controls", color_raw.get("control")),
            key="color.controls",
        )
        color_post_processing = _dict(
            color_raw.get("post_processing"), key="color.post_processing"
        )
        for filter_name in ("decimation_filter", "rotation_filter"):
            if filter_name not in color_post_processing:
                continue
            filter_config = _dict(
                color_post_processing[filter_name],
                key=f"color.post_processing.{filter_name}",
            )
            if "enabled" in filter_config:
                filter_config["enabled"] = _bool(
                    filter_config["enabled"],
                    key=f"color.post_processing.{filter_name}.enabled",
                )
            color_post_processing[filter_name] = filter_config
        color = ColorConfig(
            data_flow=_stream(
                color_df,
                field_name="color.data_flow",
                default_format="bgr8",
                default_enabled=True,
            ),
            control=ColorControlConfig(
                auto_exposure=_opt_bool(color_ctrl, "auto_exposure", prefix="color.controls"),
                exposure=_opt_float(color_ctrl.get("exposure"), key="color.controls.exposure"),
                gain=_opt_float(color_ctrl.get("gain"), key="color.controls.gain"),
                auto_white_balance=_opt_bool(
                    color_ctrl, "auto_white_balance", prefix="color.controls"
                ),
                white_balance=_opt_float(
                    color_ctrl.get("white_balance"), key="color.controls.white_balance"
                ),
                brightness=_opt_float(color_ctrl.get("brightness"), key="color.controls.brightness"),
                contrast=_opt_float(color_ctrl.get("contrast"), key="color.controls.contrast"),
                saturation=_opt_float(color_ctrl.get("saturation"), key="color.controls.saturation"),
                sharpness=_opt_float(color_ctrl.get("sharpness"), key="color.controls.sharpness"),
                gamma=_opt_float(color_ctrl.get("gamma"), key="color.controls.gamma"),
                hue=_opt_float(color_ctrl.get("hue"), key="color.controls.hue"),
                backlight_compensation=_opt_float(
                    color_ctrl.get("backlight_compensation"),
                    key="color.controls.backlight_compensation",
                ),
                power_line_frequency=_opt_float(
                    color_ctrl.get("power_line_frequency"),
                    key="color.controls.power_line_frequency",
                ),
                auto_exposure_priority=_opt_float(
                    color_ctrl.get("auto_exposure_priority"),
                    key="color.controls.auto_exposure_priority",
                ),
                global_time_enabled=_opt_float(
                    color_ctrl.get("global_time_enabled"),
                    key="color.controls.global_time_enabled",
                ),
                mirror=_bool(color_ctrl.get("mirror", False), key="color.controls.mirror"),
                flip=_bool(color_ctrl.get("flip", False), key="color.controls.flip"),
                rotate=_rotate(color_ctrl.get("rotate", 0), key="color.control.rotate"),
            ),
            options=_dict(color_raw.get("options"), key="color.options"),
            post_processing=color_post_processing,
            jpeg_quality=_int(
                color_df.get("jpeg_quality", color_raw.get("jpeg_quality", 85)),
                key="color.jpeg_quality",
            ),
        )
        if not (1 <= color.jpeg_quality <= 100):
            raise ValueError("color.jpeg_quality must be in [1, 100]")
        _validate_stream("color.data_flow", color.data_flow)

        stereo_raw = _dict(data.get("stereo_module"), key="stereo_module")
        depth_raw = _dict(data.get("depth"), key="depth")
        stereo_enabled = False
        stereo_df: dict[str, Any] = {}
        stereo_streams: dict[str, Any] = {}
        stereo_software_raw: dict[str, Any] = {}
        if stereo_raw:
            stereo_enabled = _bool(
                stereo_raw.get("enabled", True), key="stereo_module.enabled"
            )
            stereo_df = _dict(
                stereo_raw.get("data_flow"), key="stereo_module.data_flow"
            )
            stereo_streams = _dict(
                stereo_df.get("streams"), key="stereo_module.data_flow.streams"
            )
            depth_df = {
                key: stereo_df[key]
                for key in ("enabled", "width", "height", "fps", "format")
                if key in stereo_df
            }
            depth_stream = _dict(
                stereo_streams.get("depth"),
                key="stereo_module.data_flow.streams.depth",
            )
            depth_df.update(depth_stream)
            depth_stream_enabled = _bool(
                depth_stream.get("enabled", depth_df.get("enabled", True)),
                key="stereo_module.data_flow.streams.depth.enabled",
            )
            depth_df["enabled"] = stereo_enabled and depth_stream_enabled
            depth_ctrl = _dict(
                stereo_raw.get("controls", stereo_raw.get("control")),
                key="stereo_module.controls",
            )
            for key in ("emitter_enabled", "auto_exposure"):
                if key in stereo_raw:
                    depth_ctrl[key] = stereo_raw[key]
            stereo_software_raw = _dict(
                stereo_raw.get("software"), key="stereo_module.software"
            )
            depth_software = _dict(
                stereo_software_raw.get("depth"), key="stereo_module.software.depth"
            )
            depth_advanced = stereo_raw.get("advanced_controls")
            depth_options = stereo_raw.get("options")
        else:
            depth_df = _dict(depth_raw.get("data_flow"), key="depth.data_flow")
            depth_ctrl = _dict(
                depth_raw.get("controls", depth_raw.get("control")),
                key="depth.controls",
            )
            depth_software = {}
            depth_advanced = depth_raw.get("advanced_controls")
            depth_options = depth_raw.get("options")

        depth_control_prefix = "stereo_module.controls" if stereo_raw else "depth.controls"
        depth_software_prefix = (
            "stereo_module.software.depth" if stereo_raw else "depth.controls"
        )
        advanced_controls_key = (
            "stereo_module.advanced_controls"
            if stereo_raw
            else "depth.advanced_controls"
        )
        advanced_controls = _dict(depth_advanced, key=advanced_controls_key)
        for group_name, raw_group in tuple(advanced_controls.items()):
            if raw_group is None:
                continue
            group = _dict(
                raw_group, key=f"{advanced_controls_key}.{group_name}"
            )
            normalized_group = str(group_name).strip().lower().replace("-", "_").replace(" ", "_")
            if normalized_group == "rsm":
                for field_name, value in tuple(group.items()):
                    normalized_field = str(field_name).strip().lower().replace("-", "_").replace(" ", "_")
                    if normalized_field == "rsm_bypass" and value is not None:
                        group[field_name] = _bool(
                            value,
                            key=f"{advanced_controls_key}.{group_name}.{field_name}",
                        )
            advanced_controls[group_name] = group
        depth_control_keys = {
            "visual_preset",
            "auto_exposure",
            "depth_auto_exposure_mode",
            "exposure",
            "gain",
            "laser_power",
            "emitter_enabled",
            "emitter_on_off",
            "depth_units",
            "inter_cam_sync_mode",
            "min_mm",
            "max_mm",
            "mirror",
            "flip",
            "rotate",
        }
        stereo_control_options = {
            key: value for key, value in depth_ctrl.items() if key not in depth_control_keys
        }
        depth = DepthConfig(
            data_flow=_stream(
                depth_df,
                field_name="depth.data_flow",
                default_format="z16",
                default_enabled=True,
            ),
            control=DepthControlConfig(
                visual_preset=_opt_float(
                    depth_ctrl.get("visual_preset"), key=f"{depth_control_prefix}.visual_preset"
                ),
                auto_exposure=_opt_bool(
                    depth_ctrl, "auto_exposure", prefix=depth_control_prefix
                ),
                depth_auto_exposure_mode=_opt_float(
                    depth_ctrl.get("depth_auto_exposure_mode"),
                    key=f"{depth_control_prefix}.depth_auto_exposure_mode",
                ),
                exposure=_opt_float(
                    depth_ctrl.get("exposure"), key=f"{depth_control_prefix}.exposure"
                ),
                gain=_opt_float(depth_ctrl.get("gain"), key=f"{depth_control_prefix}.gain"),
                laser_power=_opt_float(
                    depth_ctrl.get("laser_power"), key=f"{depth_control_prefix}.laser_power"
                ),
                emitter_enabled=_opt_float(
                    depth_ctrl.get("emitter_enabled"),
                    key=f"{depth_control_prefix}.emitter_enabled",
                ),
                emitter_on_off=_opt_float(
                    depth_ctrl.get("emitter_on_off"),
                    key=f"{depth_control_prefix}.emitter_on_off",
                ),
                depth_units=_opt_float(
                    depth_ctrl.get("depth_units"), key=f"{depth_control_prefix}.depth_units"
                ),
                inter_cam_sync_mode=_opt_float(
                    depth_ctrl.get("inter_cam_sync_mode"),
                    key=f"{depth_control_prefix}.inter_cam_sync_mode",
                ),
                min_mm=_int(
                    depth_software.get("min_mm", depth_ctrl.get("min_mm", 100)),
                    key=f"{depth_software_prefix}.min_mm",
                ),
                max_mm=_int(
                    depth_software.get("max_mm", depth_ctrl.get("max_mm", 10000)),
                    key=f"{depth_software_prefix}.max_mm",
                ),
                mirror=_bool(
                    depth_software.get("mirror", depth_ctrl.get("mirror", False)),
                    key=f"{depth_software_prefix}.mirror",
                ),
                flip=_bool(
                    depth_software.get("flip", depth_ctrl.get("flip", False)),
                    key=f"{depth_software_prefix}.flip",
                ),
                rotate=_rotate(
                    depth_software.get("rotate", depth_ctrl.get("rotate", 0)),
                    key="stereo_module.software.depth.rotate" if stereo_raw else "depth.control.rotate",
                ),
            ),
            options={**stereo_control_options, **_dict(depth_options, key="stereo_module.options" if stereo_raw else "depth.options")},
            advanced_controls=advanced_controls,
        )
        _validate_stream("depth.data_flow", depth.data_flow)
        if depth.control.min_mm < 0:
            raise ValueError("depth.control.min_mm must be >= 0")
        if depth.control.max_mm <= depth.control.min_mm:
            raise ValueError("depth.control.max_mm must be greater than min_mm")

        if stereo_raw:
            def _stereo_ir_stream(stream_key: str, software_key: str) -> dict[str, Any]:
                raw = {
                    key: stereo_df[key]
                    for key in ("width", "height", "fps")
                    if key in stereo_df
                }
                stream_raw = _dict(
                    stereo_streams.get(stream_key),
                    key=f"stereo_module.data_flow.streams.{stream_key}",
                )
                raw.update(stream_raw)
                stream_enabled = _bool(
                    stream_raw.get("enabled", True),
                    key=f"stereo_module.data_flow.streams.{stream_key}.enabled",
                )
                raw["enabled"] = stereo_enabled and stream_enabled
                raw.update(
                    _dict(
                        stereo_software_raw.get(software_key),
                        key=f"stereo_module.software.{software_key}",
                    )
                )
                return raw

            # Stereo Module controls belong on the depth sensor path only.
            # Re-applying the same options via infrared.options stalls reopen.
            ir_raw = {
                "left": _stereo_ir_stream("infrared_1", "infrared_1"),
                "right": _stereo_ir_stream("infrared_2", "infrared_2"),
                "options": {},
            }
        else:
            ir_raw = _dict(data.get("infrared"), key="infrared")

        def _ir_side(name: str, default_index: int, default_enabled: bool) -> InfraredSideConfig:
            raw = _dict(ir_raw.get(name), key=f"infrared.{name}")
            raw_format = raw.get("format", "y8")
            if not isinstance(raw_format, str):
                raise ValueError(
                    f"infrared.{name}.format must be a string, got {raw_format!r}"
                )
            side = InfraredSideConfig(
                enabled=_bool(
                    raw.get("enabled", default_enabled), key=f"infrared.{name}.enabled"
                ),
                stream_index=_int(
                    raw.get("stream_index", default_index),
                    key=f"infrared.{name}.stream_index",
                ),
                width=_int(raw.get("width", 640), key=f"infrared.{name}.width"),
                height=_int(raw.get("height", 480), key=f"infrared.{name}.height"),
                fps=_int(raw.get("fps", 30), key=f"infrared.{name}.fps"),
                format=raw_format.strip().lower(),
                mirror=_bool(raw.get("mirror", False), key=f"infrared.{name}.mirror"),
                flip=_bool(raw.get("flip", False), key=f"infrared.{name}.flip"),
                rotate=_rotate(raw.get("rotate", 0), key=f"infrared.{name}.rotate"),
                options=_dict(raw.get("options"), key=f"infrared.{name}.options"),
            )
            if side.width <= 0 or side.height <= 0 or side.fps <= 0:
                raise ValueError(f"infrared.{name} width/height/fps must be > 0")
            return side

        infrared = InfraredConfig(
            left=_ir_side("left", 1, True),
            right=_ir_side("right", 2, False),
            options=_dict(ir_raw.get("options"), key="infrared.options"),
        )
        for name, side in (("left", infrared.left), ("right", infrared.right)):
            if side.stream_index <= 0:
                raise ValueError(f"infrared.{name}.stream_index must be > 0")
        if (
            infrared.left.enabled
            and infrared.right.enabled
            and infrared.left.stream_index == infrared.right.stream_index
        ):
            raise ValueError("enabled infrared stream indexes must be distinct")

        pp_raw = _dict(
            stereo_raw.get("post_processing")
            if stereo_raw
            else depth_raw.get("post_processing", data.get("post_processing")),
            key="post_processing",
        )

        def _filter(name: str) -> FilterConfig:
            raw = pp_raw.get(name, {}) or {}
            if not isinstance(raw, dict):
                raise ValueError(f"post_processing.{name} must be a mapping")
            options = _dict(raw.get("options"), key=f"post_processing.{name}.options")
            # Backwards compatible shorthand: allow options directly under the filter.
            options.update({k: v for k, v in raw.items() if k not in ("enabled", "options")})
            return FilterConfig(
                enabled=_bool(
                    raw.get("enabled", False), key=f"post_processing.{name}.enabled"
                ),
                options=options,
            )

        align_to = data.get("align_to", "color")
        if align_to not in ("disable", "color"):
            raise ValueError(f"align_to must be disable/color, got {align_to!r}")

        point_cloud_raw = _dict(data.get("point_cloud"), key="point_cloud")
        raw_frame_id = point_cloud_raw.get("frame_id")
        if raw_frame_id is not None:
            if not isinstance(raw_frame_id, str) or not raw_frame_id.strip():
                raise ValueError("point_cloud.frame_id must be a non-empty string or null")
            raw_frame_id = raw_frame_id.strip()
        point_cloud = PointCloudConfig(
            enabled=_bool(
                point_cloud_raw.get("enabled", False),
                key="point_cloud.enabled",
            ),
            colorize=_bool(
                point_cloud_raw.get("colorize", True),
                key="point_cloud.colorize",
            ),
            frame_id=raw_frame_id,
        )

        raw_serial = data.get("device_serial") or None
        raw_advanced_mode_json = data.get("advanced_mode_json") or None
        if raw_advanced_mode_json is not None and not isinstance(
            raw_advanced_mode_json, (str, Path)
        ):
            raise ValueError("advanced_mode_json must be a path string")

        config = cls(
            device_serial=str(raw_serial) if raw_serial is not None else None,
            device_index=_int(data.get("device_index", 0), key="device_index"),
            options=_dict(data.get("options"), key="options"),
            connect_delay_ms=_int(
                data.get("connect_delay_ms", 0), key="connect_delay_ms"
            ),
            init_timeout_sec=_float(
                data.get("init_timeout_sec", 15.0), key="init_timeout_sec"
            ),
            prewarm_frames=_int(
                data.get("prewarm_frames", 0), key="prewarm_frames"
            ),
            align_to=align_to,
            advanced_mode_json=(
                str(raw_advanced_mode_json)
                if raw_advanced_mode_json is not None
                else None
            ),
            output_color=str(data.get("output_color", "image/color")),
            output_depth=str(data.get("output_depth", "image/depth")),
            output_ir_left=str(data.get("output_ir_left", "image/ir_left")),
            output_ir_right=str(data.get("output_ir_right", "image/ir_right")),
            output_point_cloud=str(data.get("output_point_cloud", "point_cloud")),
            point_cloud=point_cloud,
            color=color,
            depth=depth,
            infrared=infrared,
            post_processing=PostProcessingConfig(
                threshold_filter=_filter("threshold_filter"),
                decimation_filter=_filter("decimation_filter"),
                rotation_filter=_filter("rotation_filter"),
                hdr_merge=_filter("hdr_merge"),
                sequence_id_filter=_filter("sequence_id_filter"),
                depth_to_disparity=_filter("depth_to_disparity"),
                spatial_filter=_filter("spatial_filter"),
                temporal_filter=_filter("temporal_filter"),
                hole_filling_filter=_filter("hole_filling_filter"),
                disparity_to_depth=_filter("disparity_to_depth"),
            ),
        )

        if config.device_index < 0:
            raise ValueError("device_index must be >= 0")
        if config.connect_delay_ms < 0:
            raise ValueError("connect_delay_ms must be >= 0")
        if config.init_timeout_sec <= 0:
            raise ValueError("init_timeout_sec must be > 0")
        if config.prewarm_frames < 0:
            raise ValueError("prewarm_frames must be >= 0")

        allowed_formats = {
            "color.data_flow": {
                "bgr8",
                "bgra8",
                "rgb8",
                "rgba8",
                "yuyv",
                "raw16",
                "mjpeg",
                "jpeg",
            },
            "depth.data_flow": {"z16"},
            "infrared.left": {"y8", "y16"},
            "infrared.right": {"y8", "y16"},
        }
        for name, stream_format in (
            ("color.data_flow", config.color.data_flow.format),
            ("depth.data_flow", config.depth.data_flow.format),
            ("infrared.left", config.infrared.left.format),
            ("infrared.right", config.infrared.right.format),
        ):
            if stream_format not in allowed_formats[name]:
                supported = ", ".join(sorted(allowed_formats[name]))
                raise ValueError(
                    f"{name}.format {stream_format!r} is unsupported; expected one of: {supported}"
                )

        any_stream_enabled = any(
            (
                config.color.data_flow.enabled,
                config.depth.data_flow.enabled,
                config.infrared.left.enabled,
                config.infrared.right.enabled,
            )
        )
        if not any_stream_enabled:
            raise ValueError("at least one color, depth, or infrared stream must be enabled")
        if config.align_to == "color" and not config.color.data_flow.enabled:
            raise ValueError("align_to='color' requires color.data_flow.enabled=true")
        if config.point_cloud.enabled and not config.depth.data_flow.enabled:
            raise ValueError("point_cloud.enabled=true requires depth.data_flow.enabled=true")
        if (
            config.point_cloud.enabled
            and config.point_cloud.colorize
            and not config.color.data_flow.enabled
        ):
            raise ValueError(
                "point_cloud.colorize=true requires color.data_flow.enabled=true"
            )
        return config

    @classmethod
    def for_snapshot(
        cls,
        *,
        device_index: int = 0,
        device_serial: str | None = None,
    ) -> RealSenseConfig:
        cfg = cls()
        cfg.device_index = device_index
        cfg.device_serial = device_serial
        return cfg

    @classmethod
    def from_yaml_path(cls, path: str | Path) -> RealSenseConfig:
        p = Path(path)
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"RealSense config must be a mapping: {p}")
        return cls.from_dict(data)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> RealSenseConfig:
        if config_path is not None:
            return cls.from_yaml_path(config_path)
        env_path = os.environ.get("REALSENSE_NODE_CONFIG", "")
        if env_path:
            return cls.from_yaml_path(env_path)
        raise ValueError("Set REALSENSE_NODE_CONFIG or pass --config.")

