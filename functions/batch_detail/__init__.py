"""HTTP endpoint for batch drill-down detail."""

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
    batch_id = route_param(req, "batchId")
    return json_response(operations_service().batch_detail(ctx.active_customer_id, batch_id))
