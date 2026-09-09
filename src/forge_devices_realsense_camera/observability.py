from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from typing import Any, Protocol

from forge_common import get_logger
from forge_common.metrics import BoundedMetricsSink
from forge_common.observability import Observer

logger = get_logger(__name__)
_ENABLED_VALUE = "1"
_REPORT_INTERVAL_SEC = 5.0
ORIGIN_ID_COLOR = "realsense-camera/color"
ORIGIN_ID_DEPTH = "realsense-camera/depth"
ORIGIN_ID_IR_LEFT = "realsense-camera/ir_left"
ORIGIN_ID_IR_RIGHT = "realsense-camera/ir_right"
ORIGIN_ID_POINT_CLOUD = "realsense-camera/point_cloud"


class DoraSender(Protocol):
    def send_output(
        self,
        output_id: str,
        data: Any,
        metadata: Mapping[str, Any] | None = None,
    ) -> Any: ...


class _TrackingSender:
    def __init__(self, node: DoraSender) -> None:
        self._node = node
        self.called = False

    def send_output(
        self,
        output_id: str,
        payload: Any,
        metadata: Mapping[str, Any] | None = None,
    ) -> Any:
        self.called = True
        return self._node.send_output(output_id, payload, metadata)


class Observation:
    """Forge Common publication observation and bounded interval export."""

    def __init__(
        self,
        *,
        sink: BoundedMetricsSink | None = None,
        observer: Observer | None = None,
        report_interval_sec: float = _REPORT_INTERVAL_SEC,
    ) -> None:
        self.sink = sink or BoundedMetricsSink(max_series=1024)
        self.observer = observer or Observer(sink=self.sink)
        self._report_interval_sec = report_interval_sec
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._report,
            name="realsense-observability",
            daemon=True,
        )

    @classmethod
    def from_env(cls) -> Observation | None:
        if os.environ.get("FORGE_OBSERVABILITY") != _ENABLED_VALUE:
            return None
        return cls()

    def start(self) -> None:
        self._thread.start()

    def publish(
        self,
        node: DoraSender,
        output_id: str,
        payload: Any,
        metadata: Mapping[str, Any],
        *,
        origin_id: str,
    ) -> Any:
        sender = _TrackingSender(node)
        try:
            return self.observer.publish(
                sender,
                output_id,
                payload,
                new_origin=True,
                origin_id=origin_id,
                metadata=metadata,
            )
        except Exception:
            if sender.called:
                raise
            return node.send_output(output_id, payload, metadata)

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=0.25)

    def _report(self) -> None:
        while not self._stop.wait(self._report_interval_sec):
            self._write_snapshot()
        self._write_snapshot()

    def _write_snapshot(self) -> None:
        try:
            snapshot = self.sink.snapshot(reset=True)
            logger.info(
                "observability interval %s",
                json.dumps(snapshot, ensure_ascii=False, allow_nan=False),
            )
        except Exception:
            pass
