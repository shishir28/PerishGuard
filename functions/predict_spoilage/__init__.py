"""Azure Function entrypoint for Task 1 spoilage prediction.

The IoT Hub-compatible endpoint invokes this function with sensor telemetry.
Each event is upserted into SensorReadings, the latest batch history is
aggregated into the 24 planned features, ONNX models run inference, and a row
is appended to SpoilagePredictions.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Iterable

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

from .inference import PredictionService


_SERVICE: PredictionService | None = None


def _service() -> PredictionService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = PredictionService.from_environment()
    return _SERVICE


def _iter_events(events: func.EventHubEvent | Iterable[func.EventHubEvent]) -> Iterable[func.EventHubEvent]:
    if isinstance(events, list):
        return events
    return [events]


def main(events: func.EventHubEvent | list[func.EventHubEvent]) -> None:
    if os.getenv("DISABLE_PREDICT_SPOILAGE", "").lower() == "true":
        logging.info("predict_spoilage disabled by DISABLE_PREDICT_SPOILAGE")
        return

    service = _service()
    processed = 0

    for event in _iter_events(events):
        try:
            payload = json.loads(event.get_body().decode("utf-8"))
            prediction = service.process_reading(payload)
            processed += 1
            logging.info(
                "Predicted batch=%s risk=%s probability=%.3f hours_left=%.1f anomalies=%d critical=%d",
                prediction.batch_id,
                prediction.risk_level,
                prediction.spoilage_probability,
                prediction.estimated_hours_left,
                prediction.anomaly_count,
                prediction.critical_anomaly_count,
            )
        except Exception:
            logging.exception("Failed to process predict_spoilage event")

    logging.info("predict_spoilage processed %d event(s)", processed)
