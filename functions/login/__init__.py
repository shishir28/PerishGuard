"""Login endpoint for dashboard sessions."""

from __future__ import annotations

import json
import logging

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

try:
    from functions.auth_service import AuthService
except ModuleNotFoundError:
    from auth_service import AuthService


_SERVICE: AuthService | None = None


def _service() -> AuthService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = AuthService.from_environment()
    return _SERVICE


def main(req: "func.HttpRequest") -> "func.HttpResponse":
    try:
        body = req.get_json()
        result = _service().login(str(body.get("email", "")), str(body.get("password", "")))
        return _json(result, 200)
    except PermissionError as exc:
        return _json({"error": str(exc)}, 401)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)
    except Exception:
        logging.exception("login failed")
        return _json({"error": "Failed to sign in"}, 500)


def _json(payload: dict[str, object], status: int) -> "func.HttpResponse":
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
