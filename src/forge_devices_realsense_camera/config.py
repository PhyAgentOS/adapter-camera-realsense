"""RealSense node configuration."""

from __future__ import annotations

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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RealSenseConfig":
        """Build config from YAML data."""

        def _opt_float(value: Any) -> float | None:
            return None if value is None else float(value)

        def _opt_bool(raw: dict[str, Any], key: str) -> bool | None:
            return None if key not in raw or raw[key] is None else bool(raw[key])

        def _rotate(value: Any, *, key: str) -> int:
            rotate = int(value)
            if rotate not in (0, 90, 180, 270):
                raise ValueError(f"{key} must be one of 0/90/180/270, got {rotate}")
            return rotate

        def _stream(
            raw: dict[str, Any],
            *,
            default_format: str,
            default_enabled: bool = True,
        ) -> StreamDataFlowConfig:
            return StreamDataFlowConfig(
                enabled=bool(raw.get("enabled", default_enabled)),
                width=int(raw.get("width", 640)),
                height=int(raw.get("height", 480)),
                fps=int(raw.get("fps", 30)),
                format=str(raw.get("format", default_format)),
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

        color_raw = data.get("color", {}) or {}
        color_df = color_raw.get("data_flow", {}) or {}
        color_ctrl = color_raw.get("controls", color_raw.get("control", {})) or {}
        color = ColorConfig(
            data_flow=_stream(color_df, default_format="bgr8", default_enabled=True),
            control=ColorControlConfig(
                auto_exposure=_opt_bool(color_ctrl, "auto_exposure"),
                exposure=_opt_float(color_ctrl.get("exposure")),
                gain=_opt_float(color_ctrl.get("gain")),
                auto_white_balance=_opt_bool(color_ctrl, "auto_white_balance"),
                white_balance=_opt_float(color_ctrl.get("white_balance")),
                brightness=_opt_float(color_ctrl.get("brightness")),
                contrast=_opt_float(color_ctrl.get("contrast")),
                saturation=_opt_float(color_ctrl.get("saturation")),
                sharpness=_opt_float(color_ctrl.get("sharpness")),
                gamma=_opt_float(color_ctrl.get("gamma")),
                hue=_opt_float(color_ctrl.get("hue")),
                backlight_compensation=_opt_float(color_ctrl.get("backlight_compensation")),
                power_line_frequency=_opt_float(color_ctrl.get("power_line_frequency")),
                auto_exposure_priority=_opt_float(color_ctrl.get("auto_exposure_priority")),
                global_time_enabled=_opt_float(color_ctrl.get("global_time_enabled")),
                mirror=bool(color_ctrl.get("mirror", False)),
                flip=bool(color_ctrl.get("flip", False)),
                rotate=_rotate(color_ctrl.get("rotate", 0), key="color.control.rotate"),
            ),
            options=_dict(color_raw.get("options"), key="color.options"),
            post_processing=_dict(color_raw.get("post_processing"), key="color.post_processing"),
            jpeg_quality=int(color_df.get("jpeg_quality", color_raw.get("jpeg_quality", 85))),
        )
        if not (1 <= color.jpeg_quality <= 100):
            raise ValueError("color.jpeg_quality must be in [1, 100]")
        _validate_stream("color.data_flow", color.data_flow)

        stereo_raw = data.get("stereo_module", {}) or {}
        depth_raw = data.get("depth", {}) or {}
        if stereo_raw:
            stereo_enabled = bool(stereo_raw.get("enabled", True))
            stereo_df = stereo_raw.get("data_flow", {}) or {}
            stereo_streams = stereo_df.get("streams", {}) or {}
            depth_df = {
                key: stereo_df[key]
                for key in ("enabled", "width", "height", "fps", "format")
                if key in stereo_df
            }
            depth_stream = stereo_streams.get("depth", {}) or {}
            depth_df.update(depth_stream)
            depth_df["enabled"] = stereo_enabled and bool(depth_stream.get("enabled", depth_df.get("enabled", True)))
            depth_ctrl = dict(stereo_raw.get("controls", stereo_raw.get("control", {})) or {})
            for key in ("emitter_enabled", "auto_exposure"):
                if key in stereo_raw:
                    depth_ctrl[key] = stereo_raw[key]
            depth_software = ((stereo_raw.get("software") or {}).get("depth", {}) or {})
            depth_advanced = stereo_raw.get("advanced_controls")
            depth_options = stereo_raw.get("options")
        else:
            depth_df = depth_raw.get("data_flow", {}) or {}
            depth_ctrl = depth_raw.get("controls", depth_raw.get("control", {})) or {}
            depth_software = {}
            depth_advanced = depth_raw.get("advanced_controls")
            depth_options = depth_raw.get("options")

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
            data_flow=_stream(depth_df, default_format="z16", default_enabled=True),
            control=DepthControlConfig(
                visual_preset=_opt_float(depth_ctrl.get("visual_preset")),
                auto_exposure=_opt_bool(depth_ctrl, "auto_exposure"),
                depth_auto_exposure_mode=_opt_float(depth_ctrl.get("depth_auto_exposure_mode")),
                exposure=_opt_float(depth_ctrl.get("exposure")),
                gain=_opt_float(depth_ctrl.get("gain")),
                laser_power=_opt_float(depth_ctrl.get("laser_power")),
                emitter_enabled=_opt_float(depth_ctrl.get("emitter_enabled")),
                emitter_on_off=_opt_float(depth_ctrl.get("emitter_on_off")),
                depth_units=_opt_float(depth_ctrl.get("depth_units")),
                inter_cam_sync_mode=_opt_float(depth_ctrl.get("inter_cam_sync_mode")),
                min_mm=int(depth_software.get("min_mm", depth_ctrl.get("min_mm", 100))),
                max_mm=int(depth_software.get("max_mm", depth_ctrl.get("max_mm", 10000))),
                mirror=bool(depth_software.get("mirror", depth_ctrl.get("mirror", False))),
                flip=bool(depth_software.get("flip", depth_ctrl.get("flip", False))),
                rotate=_rotate(
                    depth_software.get("rotate", depth_ctrl.get("rotate", 0)),
                    key="stereo_module.software.depth.rotate" if stereo_raw else "depth.control.rotate",
                ),
            ),
            options={**stereo_control_options, **_dict(depth_options, key="stereo_module.options" if stereo_raw else "depth.options")},
            advanced_controls=_dict(
                depth_advanced,
                key="stereo_module.advanced_controls" if stereo_raw else "depth.advanced_controls",
            ),
        )
        _validate_stream("depth.data_flow", depth.data_flow)
        if depth.control.max_mm <= depth.control.min_mm:
            raise ValueError("depth.control.max_mm must be greater than min_mm")

        if stereo_raw:
            stereo_df = stereo_raw.get("data_flow", {}) or {}
            stereo_streams = stereo_df.get("streams", {}) or {}
            stereo_software = stereo_raw.get("software", {}) or {}

            def _stereo_ir_stream(stream_key: str, software_key: str) -> dict[str, Any]:
                raw = {
                    key: stereo_df[key]
                    for key in ("width", "height", "fps")
                    if key in stereo_df
                }
                stream_raw = stereo_streams.get(stream_key, {}) or {}
                raw.update(stream_raw)
                raw["enabled"] = stereo_enabled and bool(stream_raw.get("enabled", True))
                raw.update(stereo_software.get(software_key, {}) or {})
                return raw

            # Stereo Module controls belong on the depth sensor path only.
            # Re-applying the same options via infrared.options stalls reopen.
            ir_raw = {
                "left": _stereo_ir_stream("infrared_1", "infrared_1"),
                "right": _stereo_ir_stream("infrared_2", "infrared_2"),
                "options": {},
            }
        else:
            ir_raw = data.get("infrared", {}) or {}

        def _ir_side(name: str, default_index: int, default_enabled: bool) -> InfraredSideConfig:
            raw = ir_raw.get(name, {}) or {}
            side = InfraredSideConfig(
                enabled=bool(raw.get("enabled", default_enabled)),
                stream_index=int(raw.get("stream_index", default_index)),
                width=int(raw.get("width", 640)),
                height=int(raw.get("height", 480)),
                fps=int(raw.get("fps", 30)),
                format=str(raw.get("format", "y8")),
                mirror=bool(raw.get("mirror", False)),
                flip=bool(raw.get("flip", False)),
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

        pp_raw = (
            stereo_raw.get("post_processing")
            if stereo_raw
            else depth_raw.get("post_processing", data.get("post_processing", {}))
        ) or {}

        def _filter(name: str) -> FilterConfig:
            raw = pp_raw.get(name, {}) or {}
            if not isinstance(raw, dict):
                raise ValueError(f"post_processing.{name} must be a mapping")
            options = _dict(raw.get("options"), key=f"post_processing.{name}.options")
            # Backwards compatible shorthand: allow options directly under the filter.
            options.update({k: v for k, v in raw.items() if k not in ("enabled", "options")})
            return FilterConfig(
                enabled=bool(raw.get("enabled", False)),
                options=options,
            )

        align_to = data.get("align_to", "color")
        if align_to not in ("disable", "color"):
            raise ValueError(f"align_to must be disable/color, got {align_to!r}")

        raw_serial = data.get("device_serial") or None

        return cls(
            device_serial=str(raw_serial) if raw_serial is not None else None,
            device_index=int(data.get("device_index", 0)),
            options=_dict(data.get("options"), key="options"),
            connect_delay_ms=int(data.get("connect_delay_ms", 0)),
            init_timeout_sec=float(data.get("init_timeout_sec", 15.0)),
            prewarm_frames=int(data.get("prewarm_frames", 0)),
            align_to=align_to,
            advanced_mode_json=data.get("advanced_mode_json") or None,
            output_color=str(data.get("output_color", "image/color")),
            output_depth=str(data.get("output_depth", "image/depth")),
            output_ir_left=str(data.get("output_ir_left", "image/ir_left")),
            output_ir_right=str(data.get("output_ir_right", "image/ir_right")),
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

    @classmethod
    def for_snapshot(
        cls,
        *,
        device_index: int = 0,
        device_serial: str | None = None,
    ) -> "RealSenseConfig":
        cfg = cls()
        cfg.device_index = device_index
        cfg.device_serial = device_serial
        return cfg

    @classmethod
    def from_yaml_path(cls, path: str | Path) -> "RealSenseConfig":
        p = Path(path)
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"RealSense config must be a mapping: {p}")
        return cls.from_dict(data)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "RealSenseConfig":
        if config_path is not None:
            return cls.from_yaml_path(config_path)
        env_path = os.environ.get("REALSENSE_NODE_CONFIG", "")
        if env_path:
            return cls.from_yaml_path(env_path)
        raise ValueError("Set REALSENSE_NODE_CONFIG or pass --config.")

