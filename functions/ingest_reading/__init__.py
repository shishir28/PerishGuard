"""HTTP shim around the predict_spoilage pipeline.

Lets a synthetic generator (or any external producer) push telemetry over
HTTP without an Event Hub. Same code path as the IoT trigger: insert reading,
detect anomalies, run ONNX inference, persist prediction, dispatch alert.
"""

from __future__ import annotations

from dataclasses import asdict

try:
    from functions._http import anonymous, json_response, parse_json
    from functions.predict_spoilage.inference import PredictionService
except ModuleNotFoundError:
    from _http import anonymous, json_response, parse_json
    from predict_spoilage.inference import PredictionService


_SERVICE: PredictionService | None = None


def _service() -> PredictionService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = PredictionService.from_environment()
    return _SERVICE


@anonymous
def main(req):
    payload = parse_json(req)
    return json_response(asdict(_service().process_reading(payload)))
