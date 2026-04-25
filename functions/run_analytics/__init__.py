"""HTTP entrypoint to run the weekly analytics batch on demand."""

from __future__ import annotations

import json
import logging

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

try:
    from functions.auth_service import require_session
except ModuleNotFoundError:
    from auth_service import require_session

try:
    from functions.analytics_batch.analytics import AnalyticsBatchService
except ModuleNotFoundError:
    from analytics_batch.analytics import AnalyticsBatchService


def main(req: "func.HttpRequest") -> "func.HttpResponse":
    try:
        require_session(req)
        count = AnalyticsBatchService.from_environment().run()
        return func.HttpResponse(
            json.dumps({"reportsWritten": count}),
            status_code=200,
            mimetype="application/json",
        )
    except PermissionError as exc:
        return func.HttpResponse(
            json.dumps({"error": str(exc)}),
            status_code=401,
            mimetype="application/json",
        )
    except Exception as exc:
        logging.exception("run_analytics failed")
        return func.HttpResponse(
            json.dumps({"error": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )
