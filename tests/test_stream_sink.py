from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
from forge_msgs import Image

path = Path(__file__).resolve().parents[1] / "examples/dora_sensor_stream/test_sink.py"
spec = spec_from_file_location("camera_stream_sink", path)
sink = module_from_spec(spec)
spec.loader.exec_module(sink)


def run_sink(tmp_path, events):
    config = tmp_path / "sink.yaml"
    config.write_text("min_frames: 1\nexpected_inputs: [image/color]\n")
    with (
        mock.patch.object(sink, "Node", return_value=iter(events)),
        mock.patch("sys.argv", ["sink", "--config", str(config)]),
    ):
        return sink.main()


def test_no_frames_cannot_pass(tmp_path):
    with pytest.raises(RuntimeError, match="insufficient valid frames"):
        run_sink(tmp_path, [{"type": "STOP"}])


def test_transport_error_cannot_pass(tmp_path):
    with pytest.raises(RuntimeError, match="transport failed"):
        run_sink(tmp_path, [{"type": "ERROR", "error": "transport failed"}])


def test_malformed_frame_cannot_pass(tmp_path):
    with pytest.raises((TypeError, ValueError, KeyError)):
        run_sink(tmp_path, [{"type": "INPUT", "id": "image/color", "value": None}])


def test_valid_image_passes(tmp_path):
    value = Image.from_numpy(
        np.zeros((2, 4, 3), dtype=np.uint8), encoding="rgb8"
    ).to_arrow()
    assert (
        run_sink(
            tmp_path,
            [{"type": "INPUT", "id": "image/color", "value": value}, {"type": "STOP"}],
        )
        == 0
    )
