"""HTTP endpoint to acknowledge an anomaly event."""

from __future__ import annotations

import json
import logging

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

from functions.ops_service import OperationsService


_SERVICE: OperationsService | None = None


def _service() -> OperationsService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = OperationsService.from_environment()
    return _SERVICE


def main(req: "func.HttpRequest") -> "func.HttpResponse":
    try:
        event_id = int(req.route_params.get("eventId", "0"))
        body = req.get_json()
        customer_id = str(body.get("customerId", "")).strip()
        if event_id <= 0 or not customer_id:
            return _json({"error": "eventId route param and customerId are required"}, 400)
        result = _service().acknowledge_anomaly(customer_id, event_id)
        return _json(result, 200)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)
    except LookupError as exc:
        return _json({"error": str(exc)}, 404)
    except Exception:
        logging.exception("ack_anomaly failed")
        return _json({"error": "Failed to acknowledge anomaly"}, 500)


def _json(payload: dict[str, object], status: int) -> "func.HttpResponse":
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
