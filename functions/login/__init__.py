"""Login endpoint for dashboard sessions."""

from __future__ import annotations

try:
    from functions._http import anonymous, json_response, parse_json
    from functions.service_factory import auth_service
except ModuleNotFoundError:
    from _http import anonymous, json_response, parse_json
    from service_factory import auth_service


@anonymous
def main(req):
    body = parse_json(req, required=("email", "password"))
    return json_response(auth_service().login(body["email"], body["password"]))
