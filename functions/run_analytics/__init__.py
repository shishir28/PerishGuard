"""HTTP entrypoint to run the weekly analytics batch on demand."""

from __future__ import annotations

try:
    from functions._http import authenticated, json_response
    from functions.analytics_batch.analytics import AnalyticsBatchService
except ModuleNotFoundError:
    from _http import authenticated, json_response
    from analytics_batch.analytics import AnalyticsBatchService


@authenticated
def main(req):
    count = AnalyticsBatchService.from_environment().run()
    return json_response({"reportsWritten": count})
