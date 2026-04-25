# nl_query

Task 4 natural-language dashboard query Function.

## Endpoint

```http
POST /api/nl-query
Content-Type: application/json
```

Request:

```json
{
  "customerId": "C001",
  "question": "Which batches are at the highest spoilage risk?"
}
```

Response:

```json
{
  "sql": "SELECT ... FROM \"vw_BatchRiskSummary\" WHERE \"CustomerId\" = %s ORDER BY \"SpoilageProbability\" DESC LIMIT 50",
  "rows": [],
  "summary": "Found matching records for this customer.",
  "chart": "table"
}
```

## Behavior

- Uses Ollama to generate PostgreSQL SQL when `OLLAMA_ENDPOINT` is configured.
- Uses deterministic fallback queries when Ollama is unavailable.
- Executes with `customerId` as a parameter.
- Summarizes results with Ollama when available, otherwise uses a local template.

## Guardrails

- `SELECT` only.
- Mandatory `WHERE "CustomerId" = %s`.
- No comments.
- No semicolons or multiple statements.
- No DML, DDL, permission, backup, or restore statements.
- Query timeout is 10 seconds.
- Results are capped at 50 rows.

## Common Fallback Questions

- Risk or spoilage questions query `"vw_BatchRiskSummary"`.
- Anomaly questions query `"AnomalyEvents"`.
- General telemetry questions query `"SensorReadings"`.
