# PerishGuard Implementation Plan

This document records the original five-task plan and the current implementation status.

Current platform note: the application runtime targets PostgreSQL through `psycopg`.

## Summary

| # | Feature | Status | Main Code |
|---|---|---|---|
| 1 | Spoilage prediction, LightGBM to ONNX | Implemented | `training/`, `functions/predict_spoilage/` |
| 2 | Real-time anomaly detection | Implemented | `functions/anomaly_detection/` |
| 3 | NemoClaw multi-agent alerts | Implemented with fallback | `functions/nemoclaw_dispatch/` |
| 4 | Natural-language dashboard queries | Implemented with guardrails and live dashboard wiring | `functions/nl_query/`, `dashboard/` |
| 5 | Business intelligence analytics | Implemented with timer and HTTP trigger | `functions/analytics_batch/`, `functions/run_analytics/` |

## Task 1: Spoilage Prediction

Goal: predict spoilage probability and remaining shelf life in hours from batch sensor history.

Implemented:

- SQL schema for `SensorReadings`, `SpoilageLabels`, `SpoilagePredictions`, and `vw_BatchRiskSummary`.
- Synthetic local data generation with customer, route, carrier, packaging, and supplier metadata.
- 24-feature engineering pipeline shared by training and inference.
- LightGBM classifier and regressor.
- ONNX export and metadata generation.
- Azure Function runtime path that stores telemetry, loads batch history, runs ONNX inference, and writes predictions.

Feature groups:

- Temperature: average, max, min, standard deviation, range.
- Humidity: average, max.
- Gas: average and max for ethylene, CO2, NH3, and VOC.
- Temporal: reading count, observation hours, cold-chain break count.
- Derived: temperature exceedance, humidity-temperature interaction, gas severity index, reading density.
- Product: encoded product type and expected shelf life.

Validation:

- Classifier ROC-AUC: `1.0000` on local synthetic data.
- Regressor MAE: about `1.34h` on local synthetic data.
- ONNX inference: below `0.05ms` per call locally.

## Task 2: Real-Time Anomaly Detection

Goal: flag abnormal readings before batch-level spoilage prediction.

Implemented methods:

- Statistical 3-sigma detection against previous 24-hour rolling history.
- Product-specific temperature thresholds.
- Humidity and gas thresholds.
- Temperature rate-of-change greater than 2 C in 30 minutes.
- Shock and light exposure triggers.

Output table: `"AnomalyEvents"`.

Integration:

- Runs inside `predict_spoilage` after telemetry insert and before ONNX inference.
- Writes anomaly rows.
- Adds temperature anomaly signals into the prediction cold-chain break snapshot.
- Includes anomaly context in alert dispatch.

## Task 3: NemoClaw Multi-Agent Alerts

Goal: dispatch coordinated operational alerts when risk thresholds are crossed.

Implemented agents:

| Agent | Trigger | Action |
|---|---|---|
| Logistics | `CRITICAL` and less than 12 hours remaining | Reroute, expedite, or cold storage |
| Quality | `HIGH` or `CRITICAL` | Inspection and compliance log |
| Notify | `MEDIUM`, `HIGH`, or `CRITICAL` | Dashboard/email/SMS notification copy |

Runtime behavior:

- Builds JSON alert context from batch, prediction, and anomalies.
- Uses Ollama `/api/generate` for concise alert text when configured.
- Posts NemoClaw tasks to `/api/v1/tasks` when configured.
- Enforces per-batch cooldown through `AlertSentAt`.
- Falls back to deterministic template text when endpoints are unavailable.

## Task 4: Natural-Language Dashboard

Goal: allow plain-English questions over customer-scoped shipment data.

Implemented:

- HTTP Function at `/api/nl-query`.
- Accepts `customerId` and `question`.
- Uses Ollama for PostgreSQL SQL generation and result summarization when configured.
- Uses deterministic fallback queries when Ollama is unavailable.
- Returns SQL, rows, summary, and chart suggestion.
- React dashboard uses the same API for risk, anomaly, telemetry, and chat views.
- Customer context is selected in the UI and can also be prefilled with `?customer=<id>`.

Guardrails:

- `SELECT` only.
- Mandatory `WHERE "CustomerId" = %s`.
- Rejects comments, semicolons, multiple statements, and mutation or DDL statements.
- Query timeout: 10 seconds.
- Row cap: 50.

## Task 5: Business Intelligence

Goal: generate weekly business pattern reports.

Implemented reports:

- Route scoring.
- Carrier comparison scorecard.
- Packaging effectiveness.
- Seasonal month/day-of-week patterns.
- Vendor/supplier scoring.

Output table: `"AnalyticsReports"`.

Runtime:

- Timer Function runs Mondays at 02:00 UTC.
- HTTP Function also allows on-demand runs through `/api/run-analytics`.
- Writes JSON payload and deterministic summary per report type.
- Reports are available for downstream consumption, while the current dashboard focuses on live risk, telemetry, anomaly, and chat views.

## Dockerization

Implemented:

- `docker-compose.yml`.
- PostgreSQL 16 service.
- SQL schema init service using `psql`.
- Azurite service.
- Azure Functions image.
- Dashboard Nginx image.
- Training utility image.
- Demo tools utility image for SQLite-to-Postgres bootstrap and synthetic ingestion traffic.

Platform note: the Functions container is pinned to `linux/amd64`. The PostgreSQL, dashboard, and training services match the current Compose stack.

## Remaining Production Work

- Connect to real Azure IoT Hub credentials.
- Deploy PostgreSQL schema to the target environment.
- Deploy model artifacts with the Function app.
- Configure production Slack webhook and SMTP credentials for alert delivery.
- Configure real Ollama and NemoClaw endpoints over Tailscale.
- Add automated tests and CI.

## Demo And Bootstrap Utilities

Implemented:

- `functions/ingest_reading/` exposes the prediction pipeline over HTTP at `/api/ingest-reading`.
- `infra/seed_postgres_from_sqlite.py` loads the existing `perishguard.db` seed data into PostgreSQL.
- `infra/synthetic_generator.py` emits realistic telemetry on a loop so the live pipeline can be demonstrated without IoT Hub.

## Tier 2: Close The Loop

Implemented:

- Real Slack webhook and SMTP email alert delivery, with per-channel records in `"AlertDispatchLog"`.
- `functions/ack_anomaly/` to acknowledge `"AnomalyEvents"` rows from the dashboard.
- `functions/batch_detail/` to serve sensor history, prediction history, anomaly history, and alert history for a selected batch.
- `functions/model_performance/` plus `vw_ModelPredictionTruth` and `vw_ModelPerformanceSummary` to compare latest predictions against `WasSpoiled`.
- Dashboard support for anomaly acknowledgment, batch drill-down, alert log visibility, and model-performance reporting.
- Lightweight session auth with `AppUsers`, `UserSessions`, and `UserCustomerAccess`, plus seeded demo users and active-customer switching.
- `CustomerSettings`, `RouteLocations`, `vw_RouteRiskSummary`, and dashboard UI for route maps plus runtime threshold/alert configuration.
- `ModelTrainingRuns`, `/api/model-training`, and live ONNX artifact refresh from PostgreSQL-backed retraining.
