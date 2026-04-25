# run_analytics

HTTP trigger for manual execution of the weekly analytics batch.

## Endpoint

```http
POST /api/run-analytics
```

## Behavior

- Reuses `AnalyticsBatchService` from `functions/analytics_batch/analytics.py`.
- Generates the same route, carrier, packaging, seasonal, and vendor reports as the timer trigger.
- Returns JSON with `reportsWritten` on success.

This endpoint is intended for demos, manual refreshes, and smoke tests without waiting for the Monday 02:00 UTC schedule.
