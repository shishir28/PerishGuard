"""HTTP endpoint for model performance reporting."""

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
    return json_response(operations_service().model_performance(ctx.active_customer_id))
