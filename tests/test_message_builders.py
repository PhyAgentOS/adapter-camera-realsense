from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from forge_msgs import CompressedImage, Image

from forge_devices_realsense_camera import main as realsense_main
from forge_devices_realsense_camera import snapshot as realsense_snapshot
from forge_devices_realsense_camera.backend import RealSenseFrame, depth_units_to_metres
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


class ExampleDataflowTests(unittest.TestCase):
    def test_dora_example_is_portable_and_has_sink(self) -> None:
        example_dir = PACKAGE_ROOT / "examples" / "dora_sensor_stream"
        text = (example_dir / "dataflow.yaml").read_text(encoding="utf-8")
        self.assertIn("test_sink", text)
        self.assertIn("realsense_camera", text)
        self.assertNotIn("/" + "home/", text)

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
