# Architecture

PerishGuard is built as a batch-aware cold-chain monitoring system. Sensor readings arrive from IoT devices, are stored in PostgreSQL, evaluated for anomalies, scored by ONNX models, and surfaced through alerts, natural-language queries, analytics reports, and a dashboard.

The intended production architecture is **ONNX-first hybrid**:

- **Models score**: ONNX classifier and regressor own numeric spoilage inference.
- **Rules guard**: deterministic anomaly detection and threshold logic protect the hot path.
- **LLM explains**: Ollama is used for summaries, alert copy, and operator-facing reasoning, not as the authoritative scoring engine.

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
       ├─ Slack webhook delivery, optional
       ├─ SMTP email delivery, optional
       └─ AlertDispatchLog audit trail

PostgreSQL
  ├─ Customers
  ├─ AppUsers / UserSessions / UserCustomerAccess
  ├─ CustomerSettings
  ├─ RouteLocations
  ├─ SensorReadings
  ├─ SpoilageLabels
  ├─ SpoilagePredictions
  ├─ AnomalyEvents
  ├─ AlertDispatchLog
  ├─ AnalyticsReports
  ├─ ModelTrainingRuns
  ├─ vw_BatchRiskSummary
  ├─ vw_ModelPredictionTruth
  ├─ vw_ModelPerformanceSummary
  └─ vw_RouteRiskSummary

HTTP Functions
  ├─ ack_anomaly: operator acknowledgment write API
  ├─ batch_detail: sensor/prediction/alert drill-down read API
  ├─ customer_settings_api: risk/anomaly/alert configuration API
  ├─ ingest_reading: HTTP shim into the prediction pipeline
  ├─ login/session/logout/switch_customer: lightweight dashboard auth
  ├─ model_performance: prediction-vs-truth performance API
  ├─ model_training: retraining trigger plus run history
  ├─ nl_query: guarded text-to-SQL over customer-scoped data
  ├─ route_overview: geospatial route-risk summary API
  └─ run_analytics: on-demand analytics batch execution

React dashboard (PerishGuard Pulse)
  ├─ login and per-customer session switching
  ├─ live risk queue
  ├─ live telemetry trend
  ├─ live anomaly feed with acknowledgment
  ├─ selected-batch drill-down
  ├─ geospatial route-risk map
  ├─ runtime threshold and alert config UI
  ├─ model performance panel
  ├─ retraining controls and history
  └─ live natural-language query panel
```

## Option 1 Component Architecture

PerishGuard is easiest to reason about as three cooperating layers.

### 1. Prediction layer

This layer must stay deterministic, low-latency, and cheap to run at event scale.

- `functions/predict_spoilage/`
  - runtime orchestration entrypoint
  - inserts sensor readings
  - loads batch history
  - builds shared features
  - runs ONNX inference
  - persists predictions
- `training/features.py`
  - shared feature contract for both training and inference
- `training/models/`
  - `spoilage_classifier.onnx`
  - `shelf_life_regressor.onnx`
  - `model_metadata.json`
- `functions/anomaly_detection/`
  - deterministic temperature, humidity, gas, shock, and light rules

### 2. Decision-support layer

This layer explains what happened and suggests next action, but does not replace the scoring decision.

- `functions/nemoclaw_dispatch/`
  - builds alert context from predictions + anomalies
  - optionally calls Ollama for concise alert text
  - optionally sends tasks to NemoClaw
  - sends Slack/email alerts
- `functions/nl_query/`
  - customer-scoped operational Q&A and dashboard card queries
  - uses Ollama when available, deterministic SQL fallbacks otherwise
- Dashboard drill-down and map surfaces
  - consume structured prediction/anomaly data and LLM-authored summaries

### 3. Workflow layer

This layer turns signals into operator actions and historical reporting.

- `functions/ack_anomaly/`
- `functions/batch_detail/`
- `functions/customer_settings_api/`
- `functions/route_overview/`
- `functions/model_performance/`
- `functions/model_training/`
- `functions/analytics_batch/`
- `functions/run_analytics/`
- React dashboard (`dashboard/`)

### Responsibility boundary

Under Option 1, each layer has a strict responsibility:

| Layer | Authority | Should not do |
|---|---|---|
| Prediction | Compute spoilage probability and hours-left | Generate free-form operational reasoning |
| Decision support | Explain risk and recommend actions | Override primary model outputs silently |
| Workflow | Present, route, acknowledge, report, retrain | Recompute core spoilage logic in the UI |

## Request Flows

### Real-time telemetry scoring flow

```text
IoT / HTTP reading
  -> predict_spoilage / ingest_reading
  -> normalize payload
  -> insert SensorReadings
  -> load customer settings
  -> load batch history
  -> detect deterministic anomalies
  -> build 24-feature vector
  -> run ONNX classifier + regressor
  -> derive RiskLevel from probability thresholds
  -> insert SpoilagePredictions
  -> maybe_dispatch_alerts
       -> optional Ollama summary
       -> optional NemoClaw task dispatch
       -> optional Slack/email delivery
  -> insert AlertDispatchLog
  -> dashboard reads updated state
```

### Dashboard operational read flow

```text
Browser
  -> login/session
  -> customer-scoped API request
  -> auth_service resolves active customer
  -> API reads PostgreSQL views/tables
  -> dashboard renders risk queue, telemetry, anomalies, routes, performance
```

Primary read APIs:

- `nl_query` for risk, anomaly, telemetry, and free-form operational questions
- `batch_detail` for deep per-batch investigation
- `route_overview` for map data
- `model_performance` for post-deployment evaluation
- `customer_settings_api` for threshold and alert controls

### Explanation and operator guidance flow

```text
Prediction + anomalies + customer settings
  -> nemoclaw_dispatch builds structured alert context
  -> Ollama generates concise explanation / action guidance when available
  -> deterministic fallback text is used otherwise
  -> text is delivered to Slack/email/dashboard surfaces
```

### Retraining flow

```text
Dashboard retraining request
  -> model_training API
  -> ModelTrainingService loads PostgreSQL labels + readings
  -> training/train_spoilage_model.py reusable training functions
  -> train classifier + regressor
  -> export ONNX + model_metadata.json
  -> record ModelTrainingRuns
  -> PredictionService hot-reloads metadata on next inference
```

## Codebase Changes To Formalize Option 1

The current repo already mostly follows Option 1. The main work is to make that boundary explicit and consistent.

### Keep as-is

- ONNX models remain the authoritative inference path in `predict_spoilage`
- `training/features.py` remains the shared feature contract
- anomaly detection remains deterministic and inline
- dashboard performance views continue to evaluate persisted predictions against labels

### Clarify and strengthen

1. **Keep LLM out of core scoring**
   - Do not let Ollama directly assign spoilage probability or hours-left.
   - Keep all numeric scoring inside `PredictionService` and ONNX artifacts.

2. **Expose explanation as separate metadata**
   - Add explicit response fields like `explanation`, `recommendedAction`, and `operatorSummary`
   - Populate them in the alerting or drill-down path, not inside model inference.

3. **Preserve deterministic fallback everywhere LLM is used**
   - `nemoclaw_dispatch` and `nl_query` should always return safe, useful responses without Ollama.

4. **Keep evaluation tied to persisted predictions**
   - `vw_ModelPredictionTruth` and `vw_ModelPerformanceSummary` should remain the source of truth for model review.
   - Any LLM-authored explanation should be treated as presentation data, not evaluation data.

5. **Separate model versioning from operator guidance**
   - `ModelTrainingRuns` and `model_metadata.json` track model changes.
   - Guidance text should reference predictions, but not redefine model versions or evaluation metrics.

## Core Data Flow

1. A telemetry event includes `CustomerId`, `BatchId`, `DeviceId`, `ProductType`, timestamp, temperature, humidity, gas readings, shock, and light.
2. `predict_spoilage` normalizes the payload and writes it to `"SensorReadings"`.
3. `anomaly_detection` evaluates the latest reading against product thresholds, rolling 24-hour statistics, temperature rate-of-change, and shock/light triggers.
4. Detected anomalies are written to `"AnomalyEvents"`.
5. The Function loads ordered batch history and builds the 24-feature vector from `training/features.py`.
6. ONNX models produce spoilage probability and estimated hours left.
7. A prediction row is written to `"SpoilagePredictions"`.
8. Alert dispatch runs when risk thresholds match agent routing rules and the batch is outside the customer-configured cooldown; successful Slack/email deliveries update prediction alert status and every channel attempt is logged in `AlertDispatchLog`.
9. The dashboard authenticates into a session, resolves the active customer server-side, reads risk/anomaly/telemetry via `nl_query`, uses dedicated APIs for acknowledgment, drill-down, route maps, and settings, and can trigger weekly analytics or model retraining.

## Codebase Shape

- `predict_spoilage` is the runtime orchestrator and owns the hot path from telemetry event to persisted prediction.
- `ingest_reading` is a thin HTTP wrapper around the same prediction service used by the Event Hub trigger so demos can run without IoT Hub.
- `anomaly_detection` is a pure rules module with no storage side effects; persistence happens in `predict_spoilage`.
- `nemoclaw_dispatch` is isolated from inference so alert generation, agent routing, and real channel delivery can degrade independently through deterministic fallback and per-channel logging.
- `nl_query` drives both the free-form dashboard chat and the fixed dashboard cards from PostgreSQL, but the active customer now comes from session auth instead of the browser payload.
- `login`, `session`, `logout`, and `switch_customer` provide lightweight local auth without introducing an external identity provider for the Docker demo stack.
- `ack_anomaly`, `batch_detail`, `model_performance`, `route_overview`, and `customer_settings_api` are narrow operational APIs for dashboard workflows that should not go through text-to-SQL.
- `model_training` closes the loop by retraining directly from PostgreSQL labels/readings and hot-reloading the shared ONNX artifacts.
- `analytics_batch` is a timer-driven reporting job, and `run_analytics` exposes the same service through an HTTP trigger for demos and manual runs.
- `training/` remains intentionally separate from the production path; it uses SQLite locally, but the deployed application stack reads and writes PostgreSQL.

## Model Architecture

Training uses generated or QA-provided batch labels plus telemetry history:

- Classifier: LightGBM, balanced class weights, target `WasSpoiled`.
- Regressor: LightGBM, target `ActualShelfLifeH`.
- Export: `spoilage_classifier.onnx`, `shelf_life_regressor.onnx`, and `model_metadata.json`, with live refresh when retraining rewrites the shared model directory.
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

If Ollama or NemoClaw are unavailable, deterministic fallback text and task metadata are used. Slack webhook and SMTP email delivery are optional and controlled through environment variables, while cooldown and routing thresholds can be overridden per customer in `CustomerSettings`.

## Natural-Language Queries

`nl_query` accepts a `question` and resolves `customerId` from the authenticated session.

Guardrails:

- Only `SELECT` is allowed.
- `WHERE "CustomerId" = %s` is mandatory.
- Semicolons, comments, DML, DDL, and multi-statement payloads are rejected.
- Query timeout is 10 seconds.
- Results are capped to 50 rows.

When `OLLAMA_ENDPOINT` is missing, deterministic fallback queries handle common risk, anomaly, telemetry, and performance questions against curated PostgreSQL tables and views.

## Auth And Multi-tenancy

- Dashboard users authenticate through seeded or persisted rows in `AppUsers`.
- Session tokens are stored in `UserSessions`, and the active customer is changed through `switch_customer`.
- Customer access is enforced in the Functions app via `UserCustomerAccess`; dashboard APIs no longer trust a browser-provided `customerId`.
- Demo users are seeded for local workflows: `admin@perishguard.local` and per-customer `ops+{customer}@perishguard.local` accounts.

## Thresholds, Routes, And Retraining

- `CustomerSettings` stores per-customer risk thresholds, anomaly thresholds, and alert-routing config.
- `RouteLocations` plus `vw_RouteRiskSummary` power the geospatial route-risk map.
- `ModelTrainingRuns` records synchronous retraining triggered from the dashboard against PostgreSQL labels and readings.

## Business Analytics

`analytics_batch` writes weekly JSON reports into `"AnalyticsReports"`:

- Route scoring.
- Carrier scorecard.
- Packaging effectiveness.
- Seasonal patterns.
- Vendor/supplier scoring.

The current summaries are deterministic. Reports are currently written as global rollups with nullable `CustomerId`, even though the source data includes customer metadata.

## Demo Bootstrap

Local demos use two helper scripts under `infra/`:

- `seed_postgres_from_sqlite.py` copies the seeded SQLite dataset into PostgreSQL.
- `synthetic_generator.py` emits realistic telemetry into `/api/ingest-reading` on a loop so the live pipeline produces predictions, anomalies, and alerts.

## Deployment Topology

Local Docker Compose includes:

- PostgreSQL 16.
- SQL schema initializer using `psql`.
- Azurite for Functions storage.
- Azure Functions Python app.
- React dashboard served by Nginx.
- Training utility image.
- Demo tools container for Postgres bootstrap and synthetic traffic generation.

Platform note: the Functions container is pinned to `linux/amd64`. PostgreSQL, dashboard, and training containers align with the current Compose stack.
