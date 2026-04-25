"""Route-risk summary for geospatial dashboard rendering."""

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
        return _json(_service().route_overview(context.active_customer_id), 200)
    except PermissionError as exc:
        return _json({"error": str(exc)}, 401)
    except Exception:
        logging.exception("route_overview failed")
        return _json({"error": "Failed to load route overview"}, 500)


def _json(payload: dict[str, object], status: int) -> "func.HttpResponse":
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
