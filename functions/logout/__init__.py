"""Logout endpoint for dashboard sessions."""

from __future__ import annotations

import json
import logging

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

try:
    from functions.auth_service import AuthService, bearer_token
except ModuleNotFoundError:
    from auth_service import AuthService, bearer_token


_SERVICE: AuthService | None = None


def _service() -> AuthService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = AuthService.from_environment()
    return _SERVICE


def main(req: "func.HttpRequest") -> "func.HttpResponse":
    try:
        _service().logout(bearer_token(req))
        return _json({"ok": True}, 200)
    except PermissionError as exc:
        return _json({"error": str(exc)}, 401)
    except Exception:
        logging.exception("logout failed")
        return _json({"error": "Failed to sign out"}, 500)


def _json(payload: dict[str, object], status: int) -> "func.HttpResponse":
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
