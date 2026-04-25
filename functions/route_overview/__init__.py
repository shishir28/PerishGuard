"""Route-risk summary for geospatial dashboard rendering."""

from __future__ import annotations

try:
    from functions._http import authenticated, current_session, json_response
    from functions.service_factory import operations_service
except ModuleNotFoundError:
    from _http import authenticated, current_session, json_response
    from service_factory import operations_service


@authenticated
def main(req):
    ctx = current_session()
    return json_response(operations_service().route_overview(ctx.active_customer_id))
