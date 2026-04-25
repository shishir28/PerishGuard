# Architecture

PerishGuard is built as a batch-aware cold-chain monitoring system. Sensor readings arrive from IoT devices, are stored in PostgreSQL, evaluated for anomalies, scored by ONNX models, and surfaced through alerts, natural-language queries, analytics reports, and a dashboard.

## System View

```text
IoT devices
  │
  ▼
Azure IoT Hub / Event Hub-compatible stream
  │
  ▼
predict_spoilage Azure Function
  ├─ inserts SensorReadings
  ├─ runs anomaly_detection
  ├─ loads batch history
  ├─ runs ONNX classifier/regressor
  ├─ inserts SpoilagePredictions
  └─ calls nemoclaw_dispatch when alert thresholds are met
       ├─ Ollama alert text, optional
       ├─ NemoClaw agent tasks, optional
       └─ deterministic fallback when endpoints are unavailable

PostgreSQL
  ├─ SensorReadings
  ├─ SpoilageLabels
  ├─ SpoilagePredictions
  ├─ AnomalyEvents
  ├─ AnalyticsReports
  └─ vw_BatchRiskSummary

HTTP Functions
  ├─ nl_query: guarded text-to-SQL over customer-scoped data
  └─ analytics_batch: weekly BI report writer

React dashboard
  ├─ local fallback risk queue
  ├─ local fallback anomaly feed
  ├─ local fallback weekly insights
  └─ live natural-language query panel
```

## Core Data Flow

1. A telemetry event includes `CustomerId`, `BatchId`, `DeviceId`, `ProductType`, timestamp, temperature, humidity, gas readings, shock, and light.
2. `predict_spoilage` normalizes the payload and writes it to `"SensorReadings"`.
3. `anomaly_detection` evaluates the latest reading against product thresholds, rolling 24-hour statistics, temperature rate-of-change, and shock/light triggers.
4. Detected anomalies are written to `"AnomalyEvents"`.
5. The Function loads ordered batch history and builds the 24-feature vector from `training/features.py`.
6. ONNX models produce spoilage probability and estimated hours left.
7. A prediction row is written to `"SpoilagePredictions"`.
8. Alert dispatch runs when risk thresholds match agent routing rules and the batch is outside cooldown.
9. The dashboard and natural-language endpoint read customer-scoped tables and views.

## Codebase Shape

- `predict_spoilage` is the runtime orchestrator and owns the hot path from telemetry event to persisted prediction.
- `anomaly_detection` is a pure rules module with no storage side effects; persistence happens in `predict_spoilage`.
- `nemoclaw_dispatch` is isolated from inference so alert generation and agent routing can degrade independently through deterministic fallback.
- `nl_query` is the only user-facing HTTP API in the repository today.
- `analytics_batch` is a timer-driven reporting job that writes JSONB reports for later consumption.
- `training/` remains intentionally separate from the production path; it uses SQLite locally, but the deployed application stack reads and writes PostgreSQL.

## Model Architecture

Training uses generated or QA-provided batch labels plus telemetry history:

- Classifier: LightGBM, balanced class weights, target `WasSpoiled`.
- Regressor: LightGBM, target `ActualShelfLifeH`.
- Export: `spoilage_classifier.onnx`, `shelf_life_regressor.onnx`, and `model_metadata.json`.
- Runtime: ONNX Runtime in Azure Functions.

The feature contract is shared between training and inference through `training/features.py`.

## Anomaly Detection

Anomalies are deterministic and run inline before prediction:

- Statistical: 3-sigma deviation from the previous 24 hours.
- Threshold: product-specific safe temperature ceilings plus humidity and gas limits.
- Rate-of-change: temperature rise greater than 2 C within 30 minutes.
- Binary triggers: shock and light exposure.

Critical anomalies are included in alert context for Task 3.

## Alerting

`nemoclaw_dispatch` builds JSON context from the prediction and anomalies.

Agent routing:

| Agent | Trigger | Action |
|---|---|---|
| Logistics | `CRITICAL` and less than 12 hours left | Reroute, expedite, or find cold storage |
| Quality | `HIGH` or `CRITICAL` | Inspection and compliance note |
| Notify | `MEDIUM`, `HIGH`, or `CRITICAL` | Dashboard, email, and SMS copy |

If Ollama or NemoClaw are unavailable, deterministic fallback text and task metadata are used.

## Natural-Language Queries

`nl_query` accepts a `customerId` and `question`.

Guardrails:

- Only `SELECT` is allowed.
- `WHERE "CustomerId" = %s` is mandatory.
- Semicolons, comments, DML, DDL, and multi-statement payloads are rejected.
- Query timeout is 10 seconds.
- Results are capped to 50 rows.

When `OLLAMA_ENDPOINT` is missing, deterministic fallback queries handle common risk, anomaly, and telemetry questions against curated PostgreSQL tables and views.

## Business Analytics

`analytics_batch` writes weekly JSON reports into `"AnalyticsReports"`:

- Route scoring.
- Carrier scorecard.
- Packaging effectiveness.
- Seasonal patterns.
- Vendor/supplier scoring.

The current summaries are deterministic. Reports are currently written as global rollups with nullable `CustomerId`, even though the source data includes customer metadata.

## Deployment Topology

Local Docker Compose includes:

- PostgreSQL 16.
- SQL schema initializer using `psql`.
- Azurite for Functions storage.
- Azure Functions Python app.
- React dashboard served by Nginx.
- Training utility image.

Platform note: the Functions container is pinned to `linux/amd64`. PostgreSQL, dashboard, and training containers align with the current Compose stack.
