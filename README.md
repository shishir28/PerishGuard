# PerishGuard

PerishGuard is a cold-chain monitoring platform for perishable shipments. It combines Azure Functions ingestion, deterministic anomaly detection, ONNX spoilage inference, multi-agent alerting, guarded natural-language analytics, weekly business reporting, and a React dashboard backed by PostgreSQL.

## Current Status

Implemented locally:

- Task 1: LightGBM spoilage classifier and shelf-life regressor exported to ONNX.
- Task 2: Real-time anomaly detection for telemetry readings.
- Task 3: NemoClaw/Ollama alert dispatcher with deterministic fallback.
- Task 4: Guarded natural-language dashboard query endpoint for PostgreSQL.
- Task 5: Weekly analytics report generation.
- React + Vite + Recharts dashboard with Nginx proxying to Azure Functions.
- Docker assets for PostgreSQL, Azurite, Azure Functions, dashboard, and training.

Validation completed:

- Python compile checks passed.
- Local synthetic DB seeding passed.
- Model training/export passed with ROC-AUC `1.0000`, MAE about `1.34h`, and ONNX inference below `0.05ms`.
- Dashboard production build passed.
- Docker dashboard and training images built successfully.
- The Functions container is pinned to `linux/amd64`; PostgreSQL, dashboard, and training services match the current Compose stack.

## Stack

- Ingest: Azure IoT Hub-compatible Event Hub trigger.
- Compute: Azure Functions, Python 3, ONNX Runtime.
- Storage: PostgreSQL in the app stack; SQLite for local training and model seeding.
- Data access: `psycopg` and PostgreSQL SQL with quoted identifiers.
- ML: LightGBM classifier/regressor exported to ONNX.
- AI: Ollama Llama 3.3 and NemoClaw over Tailscale, with deterministic local fallbacks.
- Frontend: React 19, Vite 7, Recharts 3, Nginx in Docker.
- Local services: Docker Compose, PostgreSQL, Azurite.

## Architecture Highlights

- `functions/predict_spoilage/` is the ingestion entrypoint. It normalizes telemetry, stores readings in PostgreSQL, runs anomaly detection, performs ONNX inference, persists predictions, and triggers alert dispatch.
- `functions/anomaly_detection/` runs deterministic checks on thresholds, statistical deviation, temperature rate-of-change, and shock/light triggers before prediction is finalized.
- `functions/nemoclaw_dispatch/` converts prediction plus anomaly context into alert copy and optional NemoClaw task dispatch, with cooldown handling and template fallback.
- `functions/nl_query/` is the current HTTP API surface. It translates customer-scoped questions into guarded PostgreSQL `SELECT` queries, executes them with statement timeouts, and returns rows plus a summary and chart hint.
- `functions/analytics_batch/` generates weekly JSON reports from shipment labels and latest risk summaries and stores them in `AnalyticsReports`.
- `dashboard/` is currently a hybrid UI: the natural-language panel calls the live backend, while risk, trend, anomaly, and insight widgets still use local fallback data.

## Layout

```text
PerishGuard/
├── architecture.md                  # System architecture
├── docker-compose.yml               # Local container stack
├── sql/                             # PostgreSQL schema and view definitions
├── training/                        # Synthetic data, features, training, ONNX export
│   └── models/                      # Generated model artifacts, ignored except .gitkeep
├── functions/
│   ├── predict_spoilage/            # IoT ingestion, anomaly integration, ONNX prediction
│   ├── anomaly_detection/           # Task 2 detector
│   ├── nemoclaw_dispatch/           # Task 3 alert dispatcher
│   ├── nl_query/                    # Task 4 HTTP query endpoint
│   └── analytics_batch/             # Task 5 timer endpoint
├── dashboard/                       # React dashboard and Nginx packaging
├── infra/docker/postgres/           # Postgres init helper
└── docs/                            # Implementation and Docker notes
```

## Quick Start

Local Python training:

```bash
python3 -m venv .venv
.venv/bin/pip install -r training/requirements.txt
.venv/bin/python training/seed_local_db.py --batches 400
.venv/bin/python training/train_spoilage_model.py
```

Dashboard development:

```bash
cd dashboard
npm install
npm run dev -- --port 5173
```

Docker:

```bash
cp .env.example .env
docker compose build
docker compose up -d
```

Dashboard URL in Docker: `http://localhost:8081`.

## Documentation

- [architecture.md](architecture.md): end-to-end architecture and data flow.
- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md): original plan plus implementation status.
- [docs/DOCKER.md](docs/DOCKER.md): Docker build/run details and platform notes.
- [training/README.md](training/README.md): model training pipeline.
- [dashboard/README.md](dashboard/README.md): dashboard structure and commands.
- Function READMEs live beside each Function package.
