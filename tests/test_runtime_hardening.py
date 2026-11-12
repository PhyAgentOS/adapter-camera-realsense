from __future__ import annotations

import threading
import time
import unittest
from unittest import mock

import numpy as np

from forge_devices_realsense_camera import backend as backend_module
from forge_devices_realsense_camera import backend_realsense, snapshot
from forge_devices_realsense_camera import main as main_module
from forge_devices_realsense_camera.backend import RealSenseFrame
from forge_devices_realsense_camera.config import RealSenseConfig


class FrameFreshnessTests(unittest.TestCase):
    @staticmethod
    def _bare_backend(frame: RealSenseFrame | None = None):
        backend = backend_realsense.RealSenseBackend.__new__(
            backend_realsense.RealSenseBackend
        )
        backend._lock = threading.Lock()
        backend._frame_condition = threading.Condition(backend._lock)
        backend._terminal_error = None
        backend._latest_frame = frame
        backend._thread = mock.Mock(is_alive=mock.Mock(return_value=True))
        return backend

    def test_terminal_error_invalidates_cached_frame(self) -> None:
        stale = RealSenseFrame(None, None, None, None, capture_sequence=7)
        backend = self._bare_backend(stale)

        backend._record_terminal_error("device disconnected")

        self.assertIsNone(backend._latest_frame)
        with self.assertRaisesRegex(RuntimeError, "device disconnected"):
            backend.capture_frame()

    def test_capture_can_wait_for_strictly_newer_sequence(self) -> None:
        first = RealSenseFrame(None, None, None, None, capture_sequence=1)
        second = RealSenseFrame(None, None, None, None, capture_sequence=2)
        backend = self._bare_backend(first)

        def publish() -> None:
            time.sleep(0.02)
            with backend._frame_condition:
                backend._latest_frame = second
                backend._frame_condition.notify_all()

        producer = threading.Thread(target=publish)
        producer.start()
        try:
            self.assertIs(
                backend.capture_frame(after_sequence=1, timeout_sec=1.0), second
            )
        finally:
            producer.join()


class SnapshotHardeningTests(unittest.TestCase):
    def test_snapshot_uses_distinct_frames_and_accepts_dark_scene(self) -> None:
        class FakeBackend:
            def __init__(self) -> None:
                self.after_sequences: list[int | None] = []
                self.closed = False

            def capture_frame(
                self,
                *,
                after_sequence: int | None = None,
                timeout_sec: float = 5.0,
            ) -> RealSenseFrame:
                del timeout_sec
                self.after_sequences.append(after_sequence)
                sequence = (after_sequence or 0) + 1
                color = None if sequence == 3 else np.zeros((4, 4, 3), dtype=np.uint8)
                return RealSenseFrame(
                    color=color,
                    depth=None,
                    ir_left=None,
                    ir_right=None,
                    capture_sequence=sequence,
                )

            def close(self) -> None:
                self.closed = True

        fake = FakeBackend()
        with (
            mock.patch.object(snapshot, "create_backend", return_value=fake),
            mock.patch.object(snapshot, "_write_color_jpeg") as write_jpeg,
        ):
            result = snapshot.run_snapshot(
                RealSenseConfig(),
                "dark.jpg",
                jpeg_quality=None,
                all_streams=False,
            )

        self.assertEqual(result, 0)
        self.assertEqual(fake.after_sequences, [0, 1, 2, 3])
        self.assertTrue(fake.closed)
        written = write_jpeg.call_args.args[0]
        self.assertEqual(float(written.mean()), 0.0)

    def test_snapshot_disables_unused_point_cloud_generation(self) -> None:
        config = RealSenseConfig()
        config.point_cloud.enabled = True
        backend = mock.Mock()
        backend.capture_frame.side_effect = [
            RealSenseFrame(None, None, None, None, capture_sequence=1),
            RealSenseFrame(None, None, None, None, capture_sequence=2),
            RealSenseFrame(
                np.zeros((2, 2, 3), dtype=np.uint8),
                None,
                None,
                None,
                capture_sequence=3,
            ),
        ]

        with (
            mock.patch.object(snapshot, "create_backend", return_value=backend) as create,
            mock.patch.object(snapshot, "_write_color_jpeg"),
        ):
            result = snapshot.run_snapshot(
                config,
                "snapshot.jpg",
                jpeg_quality=None,
                all_streams=False,
            )

        self.assertEqual(result, 0)
        self.assertTrue(config.point_cloud.enabled)
        captured_config = create.call_args.args[0]
        self.assertFalse(captured_config.point_cloud.enabled)

    def test_snapshot_returns_failure_when_backend_creation_fails(self) -> None:
        with mock.patch.object(
            snapshot,
            "create_backend",
            side_effect=RuntimeError("camera unavailable"),
        ):
            result = snapshot.run_snapshot(
                RealSenseConfig(),
                "snapshot.jpg",
                jpeg_quality=None,
                all_streams=False,
            )
        self.assertEqual(result, 1)

    def test_snapshot_returns_failure_when_close_fails(self) -> None:
        backend = mock.Mock()
        backend.capture_frame.side_effect = [
            RealSenseFrame(None, None, None, None, capture_sequence=1),
            RealSenseFrame(None, None, None, None, capture_sequence=2),
            RealSenseFrame(
                np.zeros((2, 2, 3), dtype=np.uint8),
                None,
                None,
                None,
                capture_sequence=3,
            ),
        ]
        backend.close.side_effect = RuntimeError("worker stuck")
        with (
            mock.patch.object(snapshot, "create_backend", return_value=backend),
            mock.patch.object(snapshot, "_write_color_jpeg"),
        ):
            result = snapshot.run_snapshot(
                RealSenseConfig(),
                "snapshot.jpg",
                jpeg_quality=None,
                all_streams=False,
            )
        self.assertEqual(result, 1)

    def test_cli_rejects_negative_device_index(self) -> None:
        with (
            mock.patch.object(
                main_module.sys,
                "argv",
                ["realsense_camera", "snapshot", "--device-index", "-1"],
            ),
            self.assertRaises(SystemExit) as raised,
        ):
            main_module._parse_args()
        self.assertEqual(raised.exception.code, 2)

    def test_main_converts_configuration_error_to_exit_code(self) -> None:
        args = mock.Mock(command="snapshot")
        with (
            mock.patch.object(main_module, "_parse_args", return_value=args),
            mock.patch.object(
                main_module,
                "_run_command",
                side_effect=ValueError("invalid config"),
            ),
        ):
            self.assertEqual(main_module.main(), 1)

    def test_cli_index_override_clears_yaml_serial(self) -> None:
        yaml_config = RealSenseConfig(device_serial="yaml-serial", device_index=9)
        with mock.patch.object(
            RealSenseConfig, "from_yaml_path", return_value=yaml_config
        ):
            resolved = snapshot.resolve_snapshot_config(
                yaml_path="camera.yaml",
                device_index=2,
                device_serial=None,
            )

        self.assertEqual(resolved.device_index, 2)
        self.assertIsNone(resolved.device_serial)


class ConfigurationHardeningTests(unittest.TestCase):
    def test_point_cloud_defaults_to_disabled(self) -> None:
        config = RealSenseConfig()

        self.assertFalse(config.point_cloud.enabled)
        self.assertTrue(config.point_cloud.colorize)
        self.assertIsNone(config.point_cloud.frame_id)
        self.assertEqual(config.output_point_cloud, "point_cloud")

    def test_point_cloud_config_requires_depth_and_color_when_enabled(self) -> None:
        with self.assertRaisesRegex(ValueError, "point_cloud.enabled.*depth"):
            RealSenseConfig.from_dict(
                {
                    "depth": {"data_flow": {"enabled": False}},
                    "point_cloud": {"enabled": True},
                }
            )

        with self.assertRaisesRegex(ValueError, "point_cloud.colorize.*color"):
            RealSenseConfig.from_dict(
                {
                    "align_to": "disable",
                    "color": {"data_flow": {"enabled": False}},
                    "point_cloud": {"enabled": True, "colorize": True},
                }
            )

    def test_xyz_point_cloud_allows_color_disabled_and_normalizes_frame_id(self) -> None:
        config = RealSenseConfig.from_dict(
            {
                "align_to": "disable",
                "color": {"data_flow": {"enabled": False}},
                "point_cloud": {
                    "enabled": True,
                    "colorize": False,
                    "frame_id": "  camera_depth_optical_frame  ",
                },
            }
        )

        self.assertTrue(config.point_cloud.enabled)
        self.assertFalse(config.point_cloud.colorize)
        self.assertEqual(
            config.point_cloud.frame_id,
            "camera_depth_optical_frame",
        )

    def test_point_cloud_booleans_and_frame_id_are_strict(self) -> None:
        with self.assertRaisesRegex(ValueError, "point_cloud.enabled"):
            RealSenseConfig.from_dict(
                {"point_cloud": {"enabled": "yes"}}
            )
        with self.assertRaisesRegex(ValueError, "point_cloud.frame_id"):
            RealSenseConfig.from_dict(
                {"point_cloud": {"frame_id": "  "}}
            )

    def test_canonical_false_string_is_not_truthy(self) -> None:
        config = RealSenseConfig.from_dict(
            {
                "align_to": "disable",
                "color": {"data_flow": {"enabled": "false"}},
            }
        )
        self.assertFalse(config.color.data_flow.enabled)

    def test_invalid_boolean_names_the_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "color.data_flow.enabled"):
            RealSenseConfig.from_dict(
                {"color": {"data_flow": {"enabled": "yes"}}}
            )

    def test_numeric_zero_and_one_remain_valid_booleans(self) -> None:
        disabled = RealSenseConfig.from_dict(
            {
                "align_to": "disable",
                "color": {"data_flow": {"enabled": 0}},
            }
        )
        enabled = RealSenseConfig.from_dict(
            {"color": {"data_flow": {"enabled": 1}}}
        )
        self.assertFalse(disabled.color.data_flow.enabled)
        self.assertTrue(enabled.color.data_flow.enabled)

    def test_fractional_integer_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "device_index"):
            RealSenseConfig.from_dict({"device_index": 1.9})

    def test_lifecycle_ranges_name_the_field(self) -> None:
        for field, value in (
            ("device_index", -1),
            ("connect_delay_ms", -1),
            ("init_timeout_sec", 0),
            ("prewarm_frames", -1),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                RealSenseConfig.from_dict({field: value})

    def test_stream_format_is_validated_per_stream(self) -> None:
        with self.assertRaisesRegex(ValueError, "depth.data_flow.format"):
            RealSenseConfig.from_dict(
                {"depth": {"data_flow": {"format": "rgb8"}}}
            )

    def test_advanced_boolean_is_strict(self) -> None:
        with self.assertRaisesRegex(ValueError, "rsm.rsm_bypass"):
            RealSenseConfig.from_dict(
                {
                    "depth": {
                        "advanced_controls": {
                            "rsm": {"rsm_bypass": "yes"}
                        }
                    }
                }
            )

    def test_advanced_boolean_alias_is_normalized_before_inversion(self) -> None:
        config = RealSenseConfig.from_dict(
            {
                "depth": {
                    "advanced_controls": {
                        "RSM": {"rsm-bypass": "false"}
                    }
                }
            }
        )
        backend = backend_realsense.RealSenseBackend.__new__(
            backend_realsense.RealSenseBackend
        )
        backend._config = config
        self.assertEqual(
            backend._advanced_mode_parameter_updates()["param-usersm"], 1
        )

    def test_at_least_one_stream_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            RealSenseConfig.from_dict(
                {
                    "align_to": "disable",
                    "color": {"data_flow": {"enabled": False}},
                    "depth": {"data_flow": {"enabled": False}},
                    "infrared": {
                        "left": {"enabled": False},
                        "right": {"enabled": False},
                    },
                }
            )

    def test_color_alignment_requires_color_stream(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires color.data_flow.enabled"):
            RealSenseConfig.from_dict(
                {"color": {"data_flow": {"enabled": False}}}
            )

    def test_enabled_ir_indexes_must_be_distinct_and_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "distinct"):
            RealSenseConfig.from_dict(
                {
                    "infrared": {
                        "left": {"enabled": True, "stream_index": 1},
                        "right": {"enabled": True, "stream_index": 1},
                    }
                }
            )
        with self.assertRaisesRegex(ValueError, "infrared.left.stream_index"):
            RealSenseConfig.from_dict(
                {"infrared": {"left": {"stream_index": 0}}}
            )


class DeviceLifecycleTests(unittest.TestCase):
    def test_retry_is_pinned_to_resolved_serial_and_resets_only_it(self) -> None:
        created_configs: list[RealSenseConfig] = []
        successful_backend = mock.sentinel.backend

        def construct(config: RealSenseConfig):
            created_configs.append(config)
            if len(created_configs) == 1:
                raise RuntimeError("initialization timed out")
            return successful_backend

        with (
            mock.patch.object(
                backend_realsense, "resolve_device_serial", return_value="selected-serial"
            ),
            mock.patch.object(
                backend_realsense, "RealSenseBackend", side_effect=construct
            ),
            mock.patch.object(backend_realsense, "hardware_reset_device") as reset,
        ):
            result = backend_module.create_backend(RealSenseConfig(device_index=1))

        self.assertIs(result, successful_backend)
        self.assertEqual(
            [config.device_serial for config in created_configs],
            ["selected-serial", "selected-serial"],
        )
        reset.assert_called_once_with("selected-serial")

    def test_hardware_reset_targets_matching_serial_only(self) -> None:
        class Device:
            def __init__(self, serial: str) -> None:
                self.serial = serial
                self.reset_count = 0

            def supports(self, _info: object) -> bool:
                return True

            def get_info(self, _info: object) -> str:
                return self.serial

            def hardware_reset(self) -> None:
                self.reset_count += 1

        first = Device("first")
        selected = Device("selected")
        context = mock.Mock()
        context.query_devices.return_value = [first, selected]
        with (
            mock.patch.object(backend_realsense.rs, "context", return_value=context),
            mock.patch.object(backend_realsense.time, "sleep"),
        ):
            backend_realsense.hardware_reset_device("selected")

        self.assertEqual(first.reset_count, 0)
        self.assertEqual(selected.reset_count, 1)

    def test_cancelled_startup_does_not_create_pipeline(self) -> None:
        backend = FrameFreshnessTests._bare_backend()
        backend._config = RealSenseConfig(connect_delay_ms=1000)
        backend._stop_event = threading.Event()
        backend._stop_event.set()
        backend._init_done = threading.Event()
        backend._init_error = None
        backend._initialized = False
        backend._pipeline = None

        with mock.patch.object(backend_realsense.rs, "pipeline") as pipeline:
            backend._capture_loop()

        pipeline.assert_not_called()
        self.assertTrue(backend._init_done.is_set())
        self.assertIn("cancelled", backend._init_error or "")

    def test_init_is_signalled_after_post_prewarm_publish(self) -> None:
        backend = FrameFreshnessTests._bare_backend()
        backend._config = RealSenseConfig(
            connect_delay_ms=0,
            prewarm_frames=2,
            align_to="disable",
        )
        backend._stop_event = threading.Event()
        backend._init_done = threading.Event()
        backend._init_error = None
        backend._initialized = False
        backend._pipeline = None
        backend._profile = None
        backend._lifecycle_lock = threading.Lock()
        backend._filters = []
        backend._depth_scale = 0.001
        backend._align = None
        backend._apply_advanced_mode_json_before_streaming = mock.Mock()
        backend._build_rs_config = mock.Mock(return_value=mock.sentinel.rs_config)
        backend._apply_sensor_options = mock.Mock()
        backend._read_depth_scale = mock.Mock(return_value=0.001)
        backend._build_filters = mock.Mock(return_value=[])
        backend._wait_for_frames = mock.Mock(
            side_effect=[
                mock.sentinel.prewarm_one,
                mock.sentinel.prewarm_two,
                mock.sentinel.first_converted,
                RuntimeError("device disconnected"),
            ]
        )

        def publish(frames: object) -> None:
            self.assertFalse(backend._init_done.is_set())
            self.assertIs(frames, mock.sentinel.first_converted)

        backend._capture_and_publish = mock.Mock(side_effect=publish)
        pipeline = mock.Mock()
        with mock.patch.object(backend_realsense.rs, "pipeline", return_value=pipeline):
            backend._capture_loop()

        backend._capture_and_publish.assert_called_once_with(
            mock.sentinel.first_converted
        )
        self.assertTrue(backend._init_done.is_set())
        self.assertTrue(backend._initialized)
        pipeline.stop.assert_called_once_with()

    def test_failed_init_cleanup_preserves_cause_and_disables_retry(self) -> None:
        backend = backend_realsense.RealSenseBackend.__new__(
            backend_realsense.RealSenseBackend
        )
        backend.close = mock.Mock(side_effect=RuntimeError("worker did not terminate"))

        with self.assertRaisesRegex(
            backend_realsense.RealSenseInitializationError,
            "initialization timed out.*Cleanup also failed",
        ) as raised:
            backend._raise_initialization_failure(
                "initialization timed out", retryable=True
            )

        self.assertFalse(raised.exception.retryable)

    def test_non_retryable_initialization_error_skips_hardware_reset(self) -> None:
        failure = backend_realsense.RealSenseInitializationError(
            "initialization timed out; worker remains alive", retryable=False
        )
        with (
            mock.patch.object(
                backend_realsense, "resolve_device_serial", return_value="selected"
            ),
            mock.patch.object(
                backend_realsense.RealSenseBackend,
                "__new__",
                side_effect=failure,
            ),
            mock.patch.object(backend_realsense, "hardware_reset_device") as reset,
        ):
            with self.assertRaises(backend_realsense.RealSenseInitializationError):
                backend_module.create_backend(RealSenseConfig())
        reset.assert_not_called()

    def test_close_reports_worker_that_cannot_terminate(self) -> None:
        backend = FrameFreshnessTests._bare_backend(
            RealSenseFrame(None, None, None, None, capture_sequence=1)
        )
        backend._stop_event = threading.Event()
        backend._thread = mock.Mock()
        backend._thread.is_alive.return_value = True

        with self.assertRaisesRegex(RuntimeError, "did not terminate"):
            backend.close()

        backend._thread.join.assert_called_once_with(timeout=5.0)
        self.assertIsNone(backend._latest_frame)

    def test_ir_only_stereo_controls_are_applied_once(self) -> None:
        config = RealSenseConfig()
        config.color.data_flow.enabled = False
        config.depth.data_flow.enabled = False
        config.infrared.left.enabled = True
        config.infrared.right.enabled = False
        config.depth.control.exposure = 123.0

        sensor = mock.sentinel.sensor
        device = mock.Mock(sensors=[sensor])
        backend = backend_realsense.RealSenseBackend.__new__(
            backend_realsense.RealSenseBackend
        )
        backend._config = config
        backend._profile = mock.Mock()
        backend._profile.get_device.return_value = device

        def has_stream(_sensor: object, stream: object) -> bool:
            return stream in (
                backend_realsense.rs.stream.depth,
                backend_realsense.rs.stream.infrared,
            )

        applied: list[dict[str, object]] = []
        with (
            mock.patch.object(backend_realsense, "_sensor_has_stream", side_effect=has_stream),
            mock.patch.object(
                backend_realsense,
                "_set_options",
                side_effect=lambda _sensor, options: applied.append(options),
            ),
        ):
            backend._apply_sensor_options()

        exposure_writes = [options for options in applied if options.get("exposure") == 123.0]
        self.assertEqual(len(exposure_writes), 1)

    def test_point_cloud_failure_does_not_drop_image_streams(self) -> None:
        backend = backend_realsense.RealSenseBackend.__new__(
            backend_realsense.RealSenseBackend
        )
        backend._config = RealSenseConfig()
        backend._config.point_cloud.enabled = True
        backend._point_cloud = mock.sentinel.point_cloud_processor
        color = np.zeros((2, 2, 3), dtype=np.uint8)
        depth = np.ones((2, 2), dtype=np.float32)
        ir = np.zeros((2, 2), dtype=np.uint8)
        processed_depth = mock.sentinel.processed_depth
        color_frame = mock.sentinel.color_frame
        backend._extract_color_source = mock.Mock(
            return_value=(color_frame, color)
        )
        backend._prepare_color_output = mock.Mock(return_value=color)
        backend._process_depth_frame = mock.Mock(return_value=processed_depth)
        backend._depth_frame_to_metres = mock.Mock(return_value=depth)
        backend._extract_point_cloud = mock.Mock(
            side_effect=RuntimeError("projection failed")
        )
        backend._orient_depth = mock.Mock(return_value=depth)
        backend._extract_ir = mock.Mock(return_value=(ir, None))
        frames = mock.Mock()
        frames.get_color_frame.return_value = None
        frames.get_depth_frame.return_value = None

        frame = backend._convert_frameset(frames)

        self.assertIs(frame.color, color)
        self.assertIs(frame.depth, depth)
        self.assertIs(frame.ir_left, ir)
        self.assertIsNone(frame.point_cloud)
        backend._process_depth_frame.assert_called_once_with(frames)
        backend._extract_point_cloud.assert_called_once_with(
            processed_depth,
            depth,
            color_frame,
            color,
        )
        backend._extract_color_source.assert_called_once_with(frames)
        backend._prepare_color_output.assert_called_once_with(color)

    def test_point_cloud_maps_color_before_calculating_processed_depth(self) -> None:
        backend = backend_realsense.RealSenseBackend.__new__(
            backend_realsense.RealSenseBackend
        )
        backend._config = RealSenseConfig()
        backend._config.point_cloud.enabled = True
        processor = mock.Mock()
        points = mock.Mock()
        points.get_vertices.return_value = np.array(
            [(0.0, 0.0, 1.0)],
            dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4")],
        )
        points.get_texture_coordinates.return_value = np.array(
            [(0.0, 0.0)],
            dtype=[("u", "<f4"), ("v", "<f4")],
        )
        processor.calculate.return_value = points
        backend._point_cloud = processor
        depth_frame = mock.sentinel.processed_depth_frame
        color_frame = mock.sentinel.color_frame

        cloud = backend._extract_point_cloud(
            depth_frame,
            np.ones((1, 1), dtype=np.float32),
            color_frame,
            np.array([[[1, 2, 3]]], dtype=np.uint8),
        )

        self.assertIsNotNone(cloud)
        self.assertEqual(
            processor.method_calls[:2],
            [mock.call.map_to(color_frame), mock.call.calculate(depth_frame)],
        )

    def test_point_cloud_processor_setup_failure_is_non_fatal(self) -> None:
        with mock.patch.object(
            backend_realsense.rs,
            "pointcloud",
            side_effect=RuntimeError("unsupported"),
        ):
            processor = backend_realsense._create_point_cloud_processor(True)

        self.assertIsNone(processor)

    def test_point_cloud_processor_is_not_created_when_disabled(self) -> None:
        with mock.patch.object(backend_realsense.rs, "pointcloud") as factory:
            processor = backend_realsense._create_point_cloud_processor(False)

        self.assertIsNone(processor)
        factory.assert_not_called()

    def test_unknown_requested_advanced_control_fails(self) -> None:
        backend = backend_realsense.RealSenseBackend.__new__(
            backend_realsense.RealSenseBackend
        )
        backend._config = RealSenseConfig()
        backend._config.depth.advanced_controls = {"depth_control": {"unknown": 1}}

        with self.assertRaisesRegex(ValueError, "unknown advanced control"):
            backend._advanced_mode_parameter_updates()


if __name__ == "__main__":
    unittest.main()
