"""HTTP entrypoint for Task 4 natural-language dashboard queries."""

from __future__ import annotations

import json
import logging
import os

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

from .query_service import NaturalLanguageQueryService


_SERVICE: NaturalLanguageQueryService | None = None


def _service() -> NaturalLanguageQueryService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = NaturalLanguageQueryService.from_environment()
    return _SERVICE


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
        question = str(body.get("question", "")).strip()
        customer_id = str(body.get("customerId", "")).strip()
        if not question or not customer_id:
            return _json_response({"error": "question and customerId are required"}, status_code=400)

        if os.getenv("DISABLE_NL_QUERY", "").lower() == "true":
            return _json_response({"error": "nl_query disabled"}, status_code=503)

        result = _service().answer(question, customer_id)
        return _json_response(result)
    except ValueError as exc:
        return _json_response({"error": str(exc)}, status_code=400)
    except Exception:
        logging.exception("nl_query failed")
        return _json_response({"error": "Failed to answer question"}, status_code=500)


def _json_response(payload: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, default=str),
        status_code=status_code,
        mimetype="application/json",
    )
