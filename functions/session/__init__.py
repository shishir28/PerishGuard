"""Current session endpoint."""

from __future__ import annotations

try:
    from functions._http import authenticated, current_session, json_response
    from functions.auth_service import serialize_context
except ModuleNotFoundError:
    from _http import authenticated, current_session, json_response
    from auth_service import serialize_context


@authenticated
def main(req):
    ctx = current_session()
    return json_response({"session": serialize_context(ctx)})
