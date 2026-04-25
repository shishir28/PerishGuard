"""Customer settings read/write API."""

from __future__ import annotations

try:
    from functions._http import authenticated, current_session, json_response, parse_json
    from functions.service_factory import operations_service
except ModuleNotFoundError:
    from _http import authenticated, current_session, json_response, parse_json
    from service_factory import operations_service


@authenticated
def main(req):
    ctx = current_session()
    if req.method == "GET":
        return json_response(operations_service().customer_settings(ctx.active_customer_id))
    if req.method == "PUT":
        payload = parse_json(req)
        return json_response(operations_service().update_customer_settings(ctx.active_customer_id, payload))
    raise NotImplementedError("Method not allowed")
