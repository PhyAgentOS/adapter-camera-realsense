from __future__ import annotations

from typing import Any
from unittest import mock

import pytest
from forge_common.metrics import BoundedMetricsSink
from forge_common.observability import Observer

from forge_devices_realsense_camera import main as main_module
from forge_devices_realsense_camera.config import RealSenseConfig
from forge_devices_realsense_camera.observability import (
    ORIGIN_ID_COLOR,
    ORIGIN_ID_DEPTH,
    ORIGIN_ID_IR_LEFT,
    ORIGIN_ID_POINT_CLOUD,
    Observation,
)


class SequenceClock:
    def __init__(self, *values: int | Exception) -> None:
        self._values = iter(values)

    def time_ns(self) -> int:
        value = next(self._values)
        if isinstance(value, Exception):
            raise value
        return value

    def monotonic_ns(self) -> int:
        return 1_000


class RecordingNode:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, Any, dict[str, Any]]] = []
        self.error = error

    def send_output(
        self,
        output_id: str,
        payload: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.calls.append((output_id, payload, dict(metadata or {})))
        if self.error is not None:
            raise self.error


def make_observation(
    clock: SequenceClock,
) -> tuple[Observation, BoundedMetricsSink]:
    sink = BoundedMetricsSink(max_series=16)
    return Observation(sink=sink, observer=Observer(clock=clock, sink=sink)), sink


@pytest.mark.parametrize("value", [None, "", "0", "true", "yes", "01", " 1", "1 "])
def test_observation_is_disabled_unless_environment_is_exactly_one(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv("FORGE_OBSERVABILITY", raising=False)
    else:
        monkeypatch.setenv("FORGE_OBSERVABILITY", value)

    assert Observation.from_env() is None


def test_observation_is_enabled_by_exact_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_OBSERVABILITY", "1")

    assert Observation.from_env() is not None


def test_outputs_are_independent_origins_linked_by_capture_timestamp() -> None:
    observation, sink = make_observation(SequenceClock(110, 120, 130, 140))
    node = RecordingNode()

    outputs = (
        ("image/color", ORIGIN_ID_COLOR),
        ("image/depth", ORIGIN_ID_DEPTH),
        ("image/ir_left", ORIGIN_ID_IR_LEFT),
        ("point_cloud", ORIGIN_ID_POINT_CLOUD),
    )
    for output_id, origin_id in outputs:
        observation.publish(
            node,
            output_id,
            object(),
            {"capture_timestamp_ns": 90, "frame_id": "camera_frame"},
            origin_id=origin_id,
        )

    assert len(node.calls) == 4
    assert [call[2]["forge_publish_time_ns"] for call in node.calls] == [110, 120, 130, 140]
    for (_, expected_origin_id), (_, _, metadata) in zip(outputs, node.calls, strict=True):
        assert metadata["forge_obs_version"] == 1
        assert metadata["forge_origin_time_ns"] == metadata["forge_publish_time_ns"]
        assert metadata["forge_origin_id"] == expected_origin_id
        assert metadata["capture_timestamp_ns"] == 90
        assert metadata["frame_id"] == "camera_frame"
    assert len({call[2]["forge_origin_id"] for call in node.calls}) == 4
    counters = sink.snapshot()["counters"]
    assert sum(row["count"] for row in counters if row["reason"] == "published") == 4


def test_custom_long_output_id_keeps_fixed_valid_origin() -> None:
    observation, _ = make_observation(SequenceClock(150))
    node = RecordingNode()
    output_id = "deployment/" + "custom-output-" * 100

    main_module._send_output(
        node,
        output_id,
        b"image",
        90,
        observation=observation,
        origin_id=ORIGIN_ID_COLOR,
    )

    assert node.calls[0][0] == output_id
    assert node.calls[0][2]["forge_origin_id"] == ORIGIN_ID_COLOR


def test_forge_observer_replaces_stale_wire_fields_and_preserves_business_metadata() -> None:
    observation, _ = make_observation(SequenceClock(200))
    node = RecordingNode()

    observation.publish(
        node,
        "image/color",
        b"image",
        {
            "capture_timestamp_ns": 150,
            "forge_obs_version": 1,
            "forge_publish_time_ns": 2,
            "forge_origin_time_ns": 1,
            "forge_origin_id": "tick-origin",
        },
        origin_id=ORIGIN_ID_COLOR,
    )

    assert node.calls[0][2] == {
        "capture_timestamp_ns": 150,
        "forge_obs_version": 1,
        "forge_publish_time_ns": 200,
        "forge_origin_time_ns": 200,
        "forge_origin_id": ORIGIN_ID_COLOR,
    }


def test_observer_pre_send_failure_falls_back_to_business_send_once() -> None:
    broken = mock.Mock()
    broken.publish.side_effect = RuntimeError("observer failed")
    observation = Observation(observer=broken)
    node = RecordingNode()

    observation.publish(
        node,
        "image/depth",
        b"depth",
        {"capture_timestamp_ns": 42},
        origin_id=ORIGIN_ID_DEPTH,
    )

    assert node.calls == [("image/depth", b"depth", {"capture_timestamp_ns": 42})]


def test_send_failure_is_propagated_unchanged_without_retry() -> None:
    failure = RuntimeError("transport failed")
    observation, sink = make_observation(SequenceClock(100))
    node = RecordingNode(error=failure)

    with pytest.raises(RuntimeError) as raised:
        observation.publish(
            node, "image/color", b"image", {}, origin_id=ORIGIN_ID_COLOR
        )

    assert raised.value is failure
    assert len(node.calls) == 1
    counters = sink.snapshot()["counters"]
    assert any(row["reason"] == "publish_failed" for row in counters)
    assert not any(row["reason"] == "published" for row in counters)


def test_metrics_are_reset_on_each_bounded_interval_report() -> None:
    sink = BoundedMetricsSink(max_series=1)
    observation = Observation(sink=sink)
    sink.increment("published", output_id="image/color")

    with mock.patch(
        "forge_devices_realsense_camera.observability.logger.info"
    ) as log_info:
        observation._write_snapshot()
        observation._write_snapshot()

    first_snapshot = log_info.call_args_list[0].args[1]
    second_snapshot = log_info.call_args_list[1].args[1]
    assert '"count": 1' in first_snapshot
    assert '"counters": []' in second_snapshot


def test_metrics_failures_do_not_change_business_send() -> None:
    sink = mock.Mock()
    sink.increment.side_effect = RuntimeError("sink failed")
    observer = Observer(clock=SequenceClock(100), sink=sink)
    observation = Observation(sink=sink, observer=observer)
    node = RecordingNode()

    observation.publish(
        node, "image/color", b"image", {}, origin_id=ORIGIN_ID_COLOR
    )
    assert len(node.calls) == 1


def test_observability_factory_failure_still_closes_backend() -> None:
    backend = mock.Mock()
    node = mock.Mock()
    node.__iter__ = mock.Mock(return_value=iter([{"type": "STOP"}]))

    with (
        mock.patch.object(main_module, "create_backend", return_value=backend),
        mock.patch.object(main_module, "Node", return_value=node),
        mock.patch.object(
            main_module.Observation,
            "from_env",
            side_effect=RuntimeError("init failed"),
        ),
    ):
        assert main_module.run_node(RealSenseConfig()) == 0

    backend.close.assert_called_once_with()


def test_observability_start_failure_closes_observation_and_backend() -> None:
    backend = mock.Mock()
    node = mock.Mock()
    node.__iter__ = mock.Mock(return_value=iter([{"type": "STOP"}]))
    observation = mock.Mock()
    observation.start.side_effect = RuntimeError("start failed")

    with (
        mock.patch.object(main_module, "create_backend", return_value=backend),
        mock.patch.object(main_module, "Node", return_value=node),
        mock.patch.object(
            main_module.Observation,
            "from_env",
            return_value=observation,
        ),
    ):
        assert main_module.run_node(RealSenseConfig()) == 0

    observation.close.assert_called_once_with()
    backend.close.assert_called_once_with()
