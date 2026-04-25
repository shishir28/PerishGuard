"""Customer settings read/write API."""

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
        if req.method == "GET":
            return _json(_service().customer_settings(context.active_customer_id), 200)
        if req.method == "PUT":
            payload = req.get_json()
            return _json(_service().update_customer_settings(context.active_customer_id, payload), 200)
        return _json({"error": "Method not allowed"}, 405)
    except PermissionError as exc:
        return _json({"error": str(exc)}, 401)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)
    except Exception:
        logging.exception("customer_settings_api failed")
        return _json({"error": "Failed to handle customer settings"}, 500)


def _json(payload: dict[str, object], status: int) -> "func.HttpResponse":
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
