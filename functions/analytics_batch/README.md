# analytics_batch

Task 5 weekly business intelligence analytics.

## Trigger

Timer trigger:

```text
0 0 2 * * MON
```

The Function runs every Monday at 02:00 UTC.

The same analytics service is also exposed through an HTTP trigger for manual runs:

```http
POST /api/run-analytics
```

## Reports

The Function writes one JSON report per report type into `"AnalyticsReports"`:

- `route`: spoilage and cold-chain patterns by origin and destination.
- `carrier`: carrier scorecard.
- `packaging`: packaging effectiveness.
- `seasonal`: month and day-of-week patterns.
- `vendor`: supplier quality scoring.

## Inputs

- `"SpoilageLabels"`
- `"vw_BatchRiskSummary"`

`SpoilageLabels` includes business metadata:

- `CustomerId`
- `Origin`
- `Destination`
- `Carrier`
- `PackagingType`
- `SupplierId`

## Output

Each report row contains:

- `CustomerId`
- `ReportType`
- `PeriodStart`
- `PeriodEnd`
- `ReportData` JSON
- `Summary`

The current implementation uses deterministic summaries. LLM executive summaries can be added later through the same `OLLAMA_ENDPOINT` fallback pattern used by `nl_query` and `nemoclaw_dispatch`.

At the moment, reports are written with nullable `CustomerId` and behave as global weekly rollups even though the source rows contain customer metadata.
