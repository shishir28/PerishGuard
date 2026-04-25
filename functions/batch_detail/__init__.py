"""HTTP endpoint for batch drill-down detail."""

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
        batch_id = str(req.route_params.get("batchId", "")).strip()
        customer_id = str(req.params.get("customerId", "")).strip()
        if not batch_id or not customer_id:
            return _json({"error": "batchId route param and customerId query param are required"}, 400)
        result = _service().batch_detail(customer_id, batch_id)
        return _json(result, 200)
    except LookupError as exc:
        return _json({"error": str(exc)}, 404)
    except Exception:
        logging.exception("batch_detail failed")
        return _json({"error": "Failed to load batch detail"}, 500)


def _json(payload: dict[str, object], status: int) -> "func.HttpResponse":
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
