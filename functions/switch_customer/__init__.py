"""Switch the active customer within an authenticated session."""

from __future__ import annotations

import json
import logging

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

try:
    from functions.auth_service import AuthService, bearer_token, serialize_context
except ModuleNotFoundError:
    from auth_service import AuthService, bearer_token, serialize_context


_SERVICE: AuthService | None = None


def _service() -> AuthService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = AuthService.from_environment()
    return _SERVICE


def main(req: "func.HttpRequest") -> "func.HttpResponse":
    try:
        body = req.get_json()
        context = _service().switch_customer(bearer_token(req), str(body.get("customerId", "")))
        return _json({"session": serialize_context(context)}, 200)
    except PermissionError as exc:
        return _json({"error": str(exc)}, 401)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)
    except Exception:
        logging.exception("switch_customer failed")
        return _json({"error": "Failed to switch customer"}, 500)


def _json(payload: dict[str, object], status: int) -> "func.HttpResponse":
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
