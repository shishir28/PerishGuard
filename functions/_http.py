"""Shared HTTP middleware for PerishGuard Azure Functions.

Authenticated handlers should look like:

    from functions._http import authenticated, current_session, json_response, parse_json

    @authenticated
    def main(req):
        body = parse_json(req, required=("question",))
        ctx = current_session()
        return json_response(_service().answer(body["question"], ctx.active_customer_id))

Anonymous handlers keep the single-argument Azure Functions signature:

    from functions._http import anonymous, json_response, parse_json

    @anonymous
    def main(req):
        body = parse_json(req, required=("email", "password"))
        return json_response(_auth_service().login(body["email"], body["password"]))

The decorator handles auth (PermissionError -> 401), input validation
(ValueError -> 400), missing resources (LookupError -> 404), method-not-allowed
(NotImplementedError -> 405), and unexpected errors (logged with traceback ->
500). Handlers stay focused on business logic.

The session context is stashed in a contextvar so decorated handlers keep the
single-parameter signature Azure Functions declares in function.json.
"""

from __future__ import annotations

import functools
import json
import logging
from contextvars import ContextVar
from typing import Any, Callable, Iterable, Optional

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

try:
    from functions.auth_service import AuthContext, require_session
except ModuleNotFoundError:
    from auth_service import AuthContext, require_session


HandlerFn = Callable[..., "func.HttpResponse"]

_session_var: ContextVar[Optional["AuthContext"]] = ContextVar("perishguard_session", default=None)


def current_session() -> "AuthContext":
    """Return the AuthContext for the current request (set by @authenticated)."""
    ctx = _session_var.get()
    if ctx is None:
        raise PermissionError("No active session")
    return ctx


def json_response(payload: Any, status: int = 200) -> "func.HttpResponse":
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )


def parse_json(
    req: "func.HttpRequest",
    *,
    required: Iterable[str] = (),
    allow_empty: bool = False,
) -> dict[str, Any]:
    """Parse JSON body and validate required fields.

    Returns {} for empty bodies when allow_empty=True. Raises ValueError on
    missing/empty required fields or invalid JSON.
    """
    body_bytes = req.get_body()
    if not body_bytes:
        if allow_empty:
            return {}
        raise ValueError("request body is required")

    try:
        payload = req.get_json()
    except ValueError as exc:
        raise ValueError("request body must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")

    missing = [name for name in required if not str(payload.get(name, "")).strip()]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")
    return payload


def route_param(
    req: "func.HttpRequest",
    name: str,
    *,
    cast: Callable[[str], Any] = str,
    required: bool = True,
) -> Any:
    raw = str(req.route_params.get(name, "")).strip()
    if not raw:
        if required:
            raise ValueError(f"{name} route parameter is required")
        return None
    try:
        return cast(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} route parameter is invalid") from exc


def _wrap(handler: HandlerFn, *, require_auth: bool) -> HandlerFn:
    handler_name = handler.__module__
    log = logging.getLogger(handler_name)

    @functools.wraps(handler)
    def wrapper(req: "func.HttpRequest") -> "func.HttpResponse":
        token = None
        try:
            if require_auth:
                ctx = require_session(req)
                token = _session_var.set(ctx)
                return handler(req)
            return handler(req)
        except PermissionError as exc:
            return json_response({"error": str(exc)}, 401)
        except ValueError as exc:
            return json_response({"error": str(exc)}, 400)
        except LookupError as exc:
            return json_response({"error": str(exc)}, 404)
        except NotImplementedError as exc:
            return json_response({"error": str(exc)}, 405)
        except Exception:
            log.exception("%s handler failed", handler_name)
            return json_response({"error": "Internal server error"}, 500)
        finally:
            if token is not None:
                _session_var.reset(token)

    return wrapper


def authenticated(handler: HandlerFn) -> HandlerFn:
    """Decorator: require valid session, expose AuthContext via current_session()."""
    return _wrap(handler, require_auth=True)


def anonymous(handler: HandlerFn) -> HandlerFn:
    """Decorator: no auth check, but apply consistent error mapping + logging."""
    return _wrap(handler, require_auth=False)
