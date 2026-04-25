"""HTTP endpoint to acknowledge an anomaly event."""

from __future__ import annotations

try:
    from functions._http import authenticated, current_session, json_response, route_param
    from functions.service_factory import operations_service
except ModuleNotFoundError:
    from _http import authenticated, current_session, json_response, route_param
    from service_factory import operations_service


@authenticated
def main(req):
    ctx = current_session()
    event_id = route_param(req, "eventId", cast=int)
    if event_id <= 0:
        raise ValueError("eventId must be positive")
    return json_response(operations_service().acknowledge_anomaly(ctx.active_customer_id, event_id))
