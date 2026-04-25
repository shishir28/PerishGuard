"""Model retraining API."""

from __future__ import annotations

try:
    from functions._http import authenticated, current_session, json_response, parse_json
    from functions.service_factory import model_training_service, operations_service
except ModuleNotFoundError:
    from _http import authenticated, current_session, json_response, parse_json
    from service_factory import model_training_service, operations_service


@authenticated
def main(req):
    ctx = current_session()
    if req.method == "GET":
        return json_response(operations_service().model_training_runs(ctx.active_customer_id))
    if req.method == "POST":
        payload = parse_json(req, allow_empty=True)
        scope = str(payload.get("scope", "global"))
        result = model_training_service().retrain(
            requested_by_user_id=ctx.user_id,
            customer_id=ctx.active_customer_id,
            scope=scope,
        )
        return json_response(result)
    raise NotImplementedError("Method not allowed")
