# Docker

PerishGuard includes Docker assets for local development and deployment rehearsal.

## Services

| Service | Purpose | Port |
|---|---|---|
| `postgres` | PostgreSQL 16 database | `5432` |
| `sql-init` | Applies `sql/*.sql` into the database | none |
| `azurite` | Azure Functions local storage emulator | `10000`, `10001`, `10002` |
| `functions` | Azure Functions Python runtime | `7071` |
| `dashboard` | React dashboard served by Nginx | `8081` |
| `training` | Utility image to seed data and regenerate models | none |
| `demo-tools` | Utility image for SQLite-to-Postgres bootstrap and synthetic HTTP telemetry | none |

## Platform Note

The Functions service is pinned to `linux/amd64`. PostgreSQL 16 Alpine, Azurite, dashboard, training, and demo-tools services follow the current Compose stack.

## Configure

```bash
cp .env.example .env
```

Defaults:

- `DISABLE_IOT_TRIGGER=true`, so the Functions app can start locally without live IoT Hub settings.
- `OLLAMA_ENDPOINT` and `NEMOCLAW_ENDPOINT` are blank, so deterministic fallbacks are used.
- Slack/email alert delivery settings are blank, so delivery attempts are logged as skipped until configured.
- PostgreSQL uses the local credentials from `.env`.
- `demo-tools` targets Postgres at `postgres:5432` and the HTTP ingest shim at `http://functions/api/ingest-reading`.

## Build

Full stack:

```bash
docker compose build
```

ARM-native subset:

```bash
docker compose build dashboard training
```

## Run

```bash
docker compose up -d
```

Open:

- Dashboard: `http://localhost:8081`
- Functions: `http://localhost:7071`
- PostgreSQL: `localhost:5432`

The dashboard proxies `/api/*` to the Functions container. For example:

- `/api/nl-query` -> `nl_query`
- `/api/anomalies/{eventId}/ack` -> `ack_anomaly`
- `/api/batches/{batchId}` -> `batch_detail`
- `/api/ingest-reading` -> `ingest_reading`
- `/api/model-performance` -> `model_performance`
- `/api/run-analytics` -> `run_analytics`

## Bootstrap Demo Data

Start the platform, then copy the seeded SQLite dataset into Postgres:

```bash
docker compose up -d
docker compose --profile tools run --rm demo-tools python infra/seed_postgres_from_sqlite.py
```

This loads the existing `perishguard.db` labels and readings into PostgreSQL so the live dashboard has data immediately.

## Generate Live Traffic

Use the demo tools container to emit realistic sensor readings into the HTTP ingestion shim:

```bash
docker compose --profile tools run --rm demo-tools \
  python infra/synthetic_generator.py --rate 5 --duration 60
```

Burst mode is also available:

```bash
docker compose --profile tools run --rm demo-tools \
  python infra/synthetic_generator.py --batches 10 --readings-per-batch 30
```

The generator drives `/api/ingest-reading`, which invokes the same prediction, anomaly, and alert pipeline used by `predict_spoilage`.

## Regenerate Models

Model artifacts are generated and ignored by Git.

```bash
docker compose --profile tools run --rm training
```

Outputs:

- `training/models/spoilage_classifier.onnx`
- `training/models/shelf_life_regressor.onnx`
- `training/models/model_metadata.json`

## Live IoT Testing

Set these in `.env`:

```bash
DISABLE_IOT_TRIGGER=false
IOT_HUB_CONNECTION=<event-hub-compatible-connection-string>
IOT_HUB_EVENT_HUB_NAME=<event-hub-compatible-name>
IOT_HUB_CONSUMER_GROUP=$$Default
```

Then restart Functions:

```bash
docker compose up -d --build functions
```

## AI Endpoints

Set these when Ollama and NemoClaw are reachable:

```bash
OLLAMA_ENDPOINT=http://<tailscale-ip>:11434
OLLAMA_MODEL=llama3.3:70b
NEMOCLAW_ENDPOINT=http://<tailscale-ip>:8080
ALERT_COOLDOWN_MINUTES=30
```

If they are blank or unavailable, the application uses deterministic fallback text and task metadata.

Optional real delivery channels:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/<team>/<channel>/<token>
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=<smtp-user>
SMTP_PASSWORD=<smtp-password>
SMTP_USE_TLS=true
SMTP_USE_SSL=false
ALERT_EMAIL_FROM=perishguard@example.com
ALERT_EMAIL_TO=ops@example.com,quality@example.com
ALERT_EMAIL_SUBJECT_PREFIX=[PerishGuard]
```

## Stop

```bash
docker compose down
```

Remove volumes:

```bash
docker compose down -v
```
