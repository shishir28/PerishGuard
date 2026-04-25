"""Timer entrypoint for Task 5 weekly analytics."""

from __future__ import annotations

import logging

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

from .analytics import AnalyticsBatchService


def main(timer: func.TimerRequest) -> None:
    service = AnalyticsBatchService.from_environment()
    count = service.run()
    logging.info("analytics_batch wrote %d report(s)", count)
