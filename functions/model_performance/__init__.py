"""HTTP endpoint for model performance reporting."""

from __future__ import annotations

import json
import logging

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

from functions.ops_service import OperationsService


_SERVICE: OperationsService | None = None


def _service() -> OperationsService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = OperationsService.from_environment()
    return _SERVICE


def main(req: "func.HttpRequest") -> "func.HttpResponse":
    try:
        customer_id = str(req.params.get("customerId", "")).strip()
        if not customer_id:
            return _json({"error": "customerId query param is required"}, 400)
        result = _service().model_performance(customer_id)
        return _json(result, 200)
    except Exception:
        logging.exception("model_performance failed")
        return _json({"error": "Failed to load model performance"}, 500)


def _json(payload: dict[str, object], status: int) -> "func.HttpResponse":
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
