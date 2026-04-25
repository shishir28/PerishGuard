"""HTTP shim around the predict_spoilage pipeline.

Lets a synthetic generator (or any external producer) push telemetry over
HTTP without an Event Hub. Same code path as the IoT trigger: insert reading,
detect anomalies, run ONNX inference, persist prediction, dispatch alert.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

try:
    from functions.predict_spoilage.inference import PredictionService
except ModuleNotFoundError:
    from predict_spoilage.inference import PredictionService


_SERVICE: PredictionService | None = None


def _service() -> PredictionService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = PredictionService.from_environment()
    return _SERVICE


def main(req: "func.HttpRequest") -> "func.HttpResponse":
    try:
        payload = req.get_json()
    except ValueError:
        return _json({"error": "request body must be JSON"}, 400)

    try:
        result = _service().process_reading(payload)
        return _json(asdict(result), 200)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)
    except Exception as exc:
        logging.exception("ingest_reading failed")
        return _json({"error": str(exc)}, 500)


def _json(payload: dict, status: int) -> "func.HttpResponse":
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
