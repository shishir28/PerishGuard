"""Logout endpoint for dashboard sessions."""

from __future__ import annotations

try:
    from functions._http import anonymous, json_response
    from functions.auth_service import bearer_token
    from functions.service_factory import auth_service
except ModuleNotFoundError:
    from _http import anonymous, json_response
    from auth_service import bearer_token
    from service_factory import auth_service


@anonymous
def main(req):
    auth_service().logout(bearer_token(req))
    return json_response({"ok": True})
