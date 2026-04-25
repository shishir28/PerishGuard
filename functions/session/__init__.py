"""Current session endpoint."""

from __future__ import annotations

import json
import logging

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

try:
    from functions.auth_service import require_session, serialize_context
except ModuleNotFoundError:
    from auth_service import require_session, serialize_context


def main(req: "func.HttpRequest") -> "func.HttpResponse":
    try:
        return _json({"session": serialize_context(require_session(req))}, 200)
    except PermissionError as exc:
        return _json({"error": str(exc)}, 401)
    except Exception:
        logging.exception("session lookup failed")
        return _json({"error": "Failed to load session"}, 500)


def _json(payload: dict[str, object], status: int) -> "func.HttpResponse":
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
