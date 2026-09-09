from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
from forge_msgs import CompressedImage, Image, PointCloudView

from forge_devices_realsense_camera import backend_realsense
from forge_devices_realsense_camera import main as realsense_main
from forge_devices_realsense_camera import snapshot as realsense_snapshot
from forge_devices_realsense_camera.backend import (
    RealSenseFrame,
    depth_units_to_metres,
)
from forge_devices_realsense_camera.config import RealSenseConfig

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class MessageBuilderTests(unittest.TestCase):
    def test_depth_units_convert_to_float32_metres_and_clip(self) -> None:
        raw = np.array([[0, 50, 100, 1000, 11000]], dtype=np.uint16)
        depth = depth_units_to_metres(
            raw,
            depth_scale=0.001,
            min_mm=100,
            max_mm=10000,
        )
        self.assertEqual(depth.dtype, np.float32)
        np.testing.assert_allclose(depth, [[0.0, 0.0, 0.1, 1.0, 0.0]])

    def test_rgb_color_uses_raw_image(self) -> None:
        config = RealSenseConfig()
        frame = RealSenseFrame(
            color=np.zeros((2, 3, 3), dtype=np.uint8),
            depth=None,
            ir_left=None,
            ir_right=None,
            timestamp_ms=123,
        )

        msg = realsense_main._frame_to_color_image(frame, config)

        self.assertIsNotNone(msg)
        decoded = Image.from_arrow(msg.to_arrow())
        self.assertEqual(decoded.width, 3)
        self.assertEqual(decoded.height, 2)
        self.assertEqual(decoded.encoding, "rgb8")
        np.testing.assert_array_equal(decoded.to_numpy(), frame.color)

    def test_jpeg_color_uses_compressed_image(self) -> None:
        config = RealSenseConfig()
        config.color.data_flow.format = "jpeg"
        config.color.jpeg_quality = 80
        frame = RealSenseFrame(
            color=np.zeros((2, 3, 3), dtype=np.uint8),
            depth=None,
            ir_left=None,
            ir_right=None,
        )

        msg = realsense_main._frame_to_color_image(frame, config)

        self.assertIsNotNone(msg)
        decoded = CompressedImage.from_arrow(msg.to_arrow())
        self.assertEqual(decoded.format, "jpeg")
        self.assertGreater(len(decoded.data), 0)

    def test_mjpeg_color_uses_compressed_image(self) -> None:
        config = RealSenseConfig()
        config.color.data_flow.format = "mjpeg"
        frame = RealSenseFrame(
            color=np.zeros((2, 3, 3), dtype=np.uint8),
            depth=None,
            ir_left=None,
            ir_right=None,
        )

        msg = realsense_main._frame_to_color_image(frame, config)

        self.assertIsNotNone(msg)
        decoded = CompressedImage.from_arrow(msg.to_arrow())
        self.assertEqual(decoded.format, "jpeg")

    def test_depth_uses_float32_metres_image(self) -> None:
        depth = (np.arange(6, dtype=np.float32) / 10).reshape(2, 3)
        frame = RealSenseFrame(color=None, depth=depth, ir_left=None, ir_right=None)

        msg = realsense_main._frame_to_depth_image(frame)

        self.assertIsNotNone(msg)
        decoded = Image.from_arrow(msg.to_arrow())
        self.assertEqual(decoded.width, 3)
        self.assertEqual(decoded.height, 2)
        self.assertEqual(decoded.encoding, "32FC1")
        self.assertEqual(decoded.to_numpy().dtype, np.float32)
        np.testing.assert_array_equal(decoded.to_numpy(), depth)

    def test_point_cloud_detaches_sdk_buffers_masks_invalid_and_maps_rgb(self) -> None:
        vertices = np.array(
            [
                (1.0, 10.0, 1.0),
                (0.0, 0.0, 0.0),
                (2.0, 20.0, 2.0),
                (3.0, 30.0, 3.0),
            ],
            dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4")],
        )
        texture = np.array(
            [(0.0, 0.0), (0.0, 0.0), (0.5, 0.0), (1.5, 0.0)],
            dtype=[("u", "<f4"), ("v", "<f4")],
        )
        depth = np.array([[1.0, 0.0], [2.0, 3.0]], dtype=np.float32)
        color = np.array(
            [
                [[10, 11, 12], [20, 21, 22]],
                [[30, 31, 32], [40, 41, 42]],
            ],
            dtype=np.uint8,
        )

        cloud = backend_realsense._point_cloud_from_sdk_buffers(
            vertices,
            texture,
            depth,
            color,
            mirror=False,
            flip=False,
            rotate=0,
        )

        self.assertEqual((cloud.width, cloud.height), (2, 2))
        self.assertFalse(cloud.is_dense)
        np.testing.assert_allclose(
            cloud.x,
            [[1.0, np.nan], [2.0, 3.0]],
            equal_nan=True,
        )
        np.testing.assert_allclose(
            cloud.y,
            [[10.0, np.nan], [20.0, 30.0]],
            equal_nan=True,
        )
        np.testing.assert_allclose(
            cloud.z,
            [[1.0, np.nan], [2.0, 3.0]],
            equal_nan=True,
        )
        self.assertIsNotNone(cloud.rgb)
        red, green, blue = cloud.rgb or ()
        np.testing.assert_array_equal(red, [[10, 0], [20, 0]])
        np.testing.assert_array_equal(green, [[11, 0], [21, 0]])
        np.testing.assert_array_equal(blue, [[12, 0], [22, 0]])
        for value in (cloud.x, cloud.y, cloud.z, red, green, blue):
            self.assertTrue(value.flags.c_contiguous)
            self.assertFalse(value.flags.writeable)

        vertices["x"] = 99.0
        color[:] = 255
        self.assertEqual(float(cloud.x[0, 0]), 1.0)
        self.assertEqual(int(red[0, 0]), 10)

        frame = RealSenseFrame(
            color=None,
            depth=depth,
            ir_left=None,
            ir_right=None,
            point_cloud=cloud,
        )
        batch_owner = realsense_main._frame_to_point_cloud(frame)
        self.assertIsNotNone(batch_owner)
        assert batch_owner is not None
        view = PointCloudView.from_arrow(batch_owner.to_arrow())
        self.assertEqual((view.width, view.height, view.point_count), (2, 2, 4))
        self.assertFalse(view.is_dense)
        self.assertTrue(view.has_rgb)
        self.assertEqual(
            view.x.__array_interface__["data"][0],
            cloud.x.__array_interface__["data"][0],
        )

    def test_point_cloud_uv_rounding_and_bounds_do_not_smear_borders(self) -> None:
        texture = np.array(
            [(-1e-8, 0.0), (1.0, 0.0), (np.nan, 0.0), (0.5, 0.5)],
            dtype=[("u", "<f4"), ("v", "<f4")],
        )
        color = np.array(
            [
                [[10, 11, 12], [20, 21, 22]],
                [[30, 31, 32], [40, 41, 42]],
            ],
            dtype=np.uint8,
        )

        red, green, blue = backend_realsense._sample_point_colors(
            texture,
            color,
            np.ones((2, 2), dtype=bool),
        )

        np.testing.assert_array_equal(red, [[10, 0], [0, 40]])
        np.testing.assert_array_equal(green, [[11, 0], [0, 41]])
        np.testing.assert_array_equal(blue, [[12, 0], [0, 42]])

    def test_point_cloud_orientation_reorders_slots_without_transforming_xyz(self) -> None:
        vertices = np.array(
            [(float(value), 0.0, 1.0) for value in range(6)],
            dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4")],
        )
        depth = np.ones((2, 3), dtype=np.float32)

        cloud = backend_realsense._point_cloud_from_sdk_buffers(
            vertices,
            None,
            depth,
            None,
            mirror=False,
            flip=False,
            rotate=90,
        )

        self.assertEqual((cloud.width, cloud.height), (2, 3))
        self.assertTrue(cloud.is_dense)
        self.assertIsNone(cloud.rgb)
        np.testing.assert_array_equal(cloud.x, [[3.0, 0.0], [4.0, 1.0], [5.0, 2.0]])

    def test_send_output_uses_same_optional_capture_metadata(self) -> None:
        node = mock.Mock()
        frame = RealSenseFrame(
            color=None,
            depth=None,
            ir_left=None,
            ir_right=None,
            capture_timestamp_ns=1_234_567_890,
        )

        for output_id in ("color", "depth", "ir_left", "ir_right"):
            realsense_main._send_output(
                node,
                output_id,
                mock.sentinel.payload,
                frame.capture_timestamp_ns,
                origin_id=realsense_main.ORIGIN_ID_COLOR,
            )

        self.assertEqual(node.send_output.call_count, 4)
        for call in node.send_output.call_args_list:
            self.assertEqual(call.kwargs["metadata"], {"capture_timestamp_ns": 1_234_567_890})

    def test_point_cloud_output_adds_configured_frame_id_metadata(self) -> None:
        node = mock.Mock()

        realsense_main._send_output(
            node,
            "point_cloud",
            mock.sentinel.payload,
            1_234_567_890,
            frame_id="camera_color_optical_frame",
            origin_id=realsense_main.ORIGIN_ID_POINT_CLOUD,
        )

        self.assertEqual(
            node.send_output.call_args.kwargs["metadata"],
            {
                "capture_timestamp_ns": 1_234_567_890,
                "frame_id": "camera_color_optical_frame",
            },
        )

    def test_point_cloud_output_failures_are_isolated(self) -> None:
        config = RealSenseConfig()
        config.point_cloud.enabled = True
        frame = RealSenseFrame(None, None, None, None)
        node = mock.Mock()

        with mock.patch.object(
            realsense_main,
            "_frame_to_point_cloud",
            side_effect=ValueError("invalid buffers"),
        ):
            self.assertFalse(
                realsense_main._send_point_cloud_output(node, frame, config)
            )
        node.send_output.assert_not_called()

        owner = mock.Mock()
        owner.to_arrow.return_value = mock.sentinel.payload
        node.send_output.side_effect = RuntimeError("output unavailable")
        with mock.patch.object(
            realsense_main,
            "_frame_to_point_cloud",
            return_value=owner,
        ):
            self.assertFalse(
                realsense_main._send_point_cloud_output(node, frame, config)
            )

    def test_cached_backend_frame_keeps_capture_timestamp(self) -> None:
        backend = backend_realsense.RealSenseBackend.__new__(
            backend_realsense.RealSenseBackend
        )
        backend._lock = threading.Lock()
        backend._frame_condition = threading.Condition(backend._lock)
        backend._terminal_error = None
        backend._thread = mock.Mock(is_alive=mock.Mock(return_value=True))
        expected = RealSenseFrame(
            color=None,
            depth=None,
            ir_left=None,
            ir_right=None,
            capture_timestamp_ns=1_234_567_890,
        )
        backend._latest_frame = expected

        first = backend.capture_frame()
        second = backend.capture_frame()

        self.assertIs(first, expected)
        self.assertIs(second, expected)
        self.assertEqual(first.capture_timestamp_ns, 1_234_567_890)
        self.assertEqual(second.capture_timestamp_ns, 1_234_567_890)

    def test_send_output_omits_missing_capture_timestamp(self) -> None:
        node = mock.Mock()

        realsense_main._send_output(
            node,
            "color",
            mock.sentinel.payload,
            None,
            origin_id=realsense_main.ORIGIN_ID_COLOR,
        )

        self.assertEqual(node.send_output.call_args.kwargs["metadata"], {})

    def test_uint8_ir_uses_mono8_image(self) -> None:
        ir = np.arange(6, dtype=np.uint8).reshape(2, 3)

        msg = realsense_main._frame_to_ir_image(ir)

        self.assertIsNotNone(msg)
        decoded = Image.from_arrow(msg.to_arrow())
        self.assertEqual(decoded.width, 3)
        self.assertEqual(decoded.height, 2)
        self.assertEqual(decoded.encoding, "mono8")
        np.testing.assert_array_equal(decoded.to_numpy(), ir)

    def test_uint16_ir_uses_raw_16uc1_image(self) -> None:
        ir = np.arange(6, dtype=np.uint16).reshape(2, 3)

        msg = realsense_main._frame_to_ir_image(ir)

        self.assertIsNotNone(msg)
        decoded = Image.from_arrow(msg.to_arrow())
        self.assertEqual(decoded.encoding, "16UC1")
        np.testing.assert_array_equal(decoded.to_numpy(), ir)

    def test_missing_frames_return_none(self) -> None:
        config = RealSenseConfig()
        frame = RealSenseFrame(color=None, depth=None, ir_left=None, ir_right=None)

        self.assertIsNone(realsense_main._frame_to_color_image(frame, config))
        self.assertIsNone(realsense_main._frame_to_depth_image(frame))
        self.assertIsNone(realsense_main._frame_to_point_cloud(frame))
        self.assertIsNone(realsense_main._frame_to_ir_image(None))

    def test_snapshot_color_jpeg_preserves_rgb_channels(self) -> None:
        rgb = np.zeros((16, 16, 3), dtype=np.uint8)
        rgb[:, :] = [255, 0, 0]

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "color.jpg"
            realsense_snapshot._write_color_jpeg(rgb, out, quality=95)
            decoded_bgr = cv2.imread(str(out), cv2.IMREAD_COLOR)

        self.assertIsNotNone(decoded_bgr)
        mean_bgr = decoded_bgr.mean(axis=(0, 1))
        self.assertGreater(mean_bgr[2], 200)
        self.assertLess(mean_bgr[0], 50)

    def test_snapshot_without_config_uses_example_config(self) -> None:
        config = realsense_snapshot.resolve_snapshot_config(
            yaml_path=None,
            device_index=None,
            device_serial=None,
        )

        self.assertEqual(config.color.data_flow.format, "rgb8")
        self.assertEqual(config.align_to, "color")
        self.assertEqual(
            realsense_snapshot._default_config_path(),
            PACKAGE_ROOT / "config" / "sensor.example.yaml",
        )
        packaged_config = (
            PACKAGE_ROOT
            / "src"
            / "forge_devices_realsense_camera"
            / "resources"
            / "sensor.example.yaml"
        )
        self.assertEqual(
            (PACKAGE_ROOT / "config" / "sensor.example.yaml").read_bytes(),
            packaged_config.read_bytes(),
        )


class ExampleDataflowTests(unittest.TestCase):
    def test_dora_example_is_portable_and_has_sink(self) -> None:
        example_dir = PACKAGE_ROOT / "examples" / "dora_sensor_stream"
        text = (example_dir / "dataflow.yaml").read_text(encoding="utf-8")
        self.assertIn("test_sink", text)
        self.assertIn("realsense_camera", text)
        self.assertNotIn("path: image_viewer", text)
        self.assertNotIn("/" + "home/", text)

        viewer_text = (example_dir / "dataflow_viewer.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("test_sink", viewer_text)
        self.assertIn("path: image_viewer", viewer_text)
        self.assertIn("id: point_cloud_renderer", viewer_text)
        self.assertIn("point_cloud: realsense_camera/point_cloud", viewer_text)
        self.assertIn(
            "image/point_cloud: point_cloud_renderer/image/point_cloud",
            viewer_text,
        )
        self.assertIn("image/color: realsense_camera/image/color", viewer_text)
        self.assertIn("image/depth: realsense_camera/image/depth", viewer_text)
        self.assertIn("image/ir_left: realsense_camera/image/ir_left", viewer_text)
        self.assertNotIn("/" + "home/", viewer_text)

    def test_only_vendor_backend_imports_sdk(self) -> None:
        source_dir = PACKAGE_ROOT / "src" / "forge_devices_realsense_camera"
        importers = []
        for path in source_dir.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "import pyrealsense2" in text:
                importers.append(path.name)
        self.assertEqual(importers, ["backend_realsense.py"])


if __name__ == "__main__":
    unittest.main()
