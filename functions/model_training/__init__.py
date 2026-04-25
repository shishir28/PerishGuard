"""Model retraining API."""

from __future__ import annotations

import json
import logging

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

try:
    from functions.auth_service import require_session
    from functions.model_training_service import ModelTrainingService
    from functions.ops_service import OperationsService
except ModuleNotFoundError:
    from auth_service import require_session
    from model_training_service import ModelTrainingService
    from ops_service import OperationsService


_OPS: OperationsService | None = None
_TRAINING: ModelTrainingService | None = None


def _ops() -> OperationsService:
    global _OPS
    if _OPS is None:
        _OPS = OperationsService.from_environment()
    return _OPS


def _training() -> ModelTrainingService:
    global _TRAINING
    if _TRAINING is None:
        _TRAINING = ModelTrainingService.from_environment()
    return _TRAINING


def main(req: "func.HttpRequest") -> "func.HttpResponse":
    try:
        context = require_session(req)
        if req.method == "GET":
            return _json(_ops().model_training_runs(context.active_customer_id), 200)
        if req.method == "POST":
            payload = req.get_json() if req.get_body() else {}
            scope = str(payload.get("scope", "global"))
            result = _training().retrain(
                requested_by_user_id=context.user_id,
                customer_id=context.active_customer_id,
                scope=scope,
            )
            return _json(result, 200)
        return _json({"error": "Method not allowed"}, 405)
    except PermissionError as exc:
        return _json({"error": str(exc)}, 401)
    except ValueError as exc:
        return _json({"error": str(exc)}, 400)
    except Exception:
        logging.exception("model_training failed")
        return _json({"error": "Failed to handle model training"}, 500)


def _json(payload: dict[str, object], status: int) -> "func.HttpResponse":
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status,
        mimetype="application/json",
    )
