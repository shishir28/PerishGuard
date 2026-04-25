"""HTTP endpoint to acknowledge an anomaly event."""

from __future__ import annotations

import json
import logging

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

try:
    from functions.auth_service import require_session
    from functions.ops_service import OperationsService
except ModuleNotFoundError:
    from auth_service import require_session
    from ops_service import OperationsService


_SERVICE: OperationsService | None = None


def _service() -> OperationsService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = OperationsService.from_environment()
    return _SERVICE


def main(req: "func.HttpRequest") -> "func.HttpResponse":
    try:
        context = require_session(req)
        event_id = int(req.route_params.get("eventId", "0"))
        if event_id <= 0:
            return _json({"error": "eventId route param is required"}, 400)
        result = _service().acknowledge_anomaly(context.active_customer_id, event_id)
        return _json(result, 200)
    except PermissionError as exc:
        return _json({"error": str(exc)}, 401)
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
