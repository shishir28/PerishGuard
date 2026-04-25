"""Switch the active customer within an authenticated session."""

from __future__ import annotations

try:
    from functions._http import anonymous, json_response, parse_json
    from functions.auth_service import bearer_token, serialize_context
    from functions.service_factory import auth_service
except ModuleNotFoundError:
    from _http import anonymous, json_response, parse_json
    from auth_service import bearer_token, serialize_context
    from service_factory import auth_service


@anonymous
def main(req):
    body = parse_json(req, required=("customerId",))
    context = auth_service().switch_customer(bearer_token(req), body["customerId"])
    return json_response({"session": serialize_context(context)})
