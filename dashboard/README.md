# PerishGuard Pulse

PerishGuard Pulse is the React + Vite + Recharts operations view for PerishGuard.

## Features

- Risk queue for active batches.
- Temperature trend chart.
- Live anomaly feed.
- Anomaly acknowledgment actions.
- Click-through batch drill-down with sensor history, prediction history, and alert log.
- Geospatial route-risk map for active customer routes.
- Threshold and alert configuration form backed by PostgreSQL customer settings.
- Model performance panel comparing latest prediction vs observed spoilage outcomes.
- Model retraining controls plus recent run history.
- Natural-language question panel that calls `/api/nl-query`.
- Login/session handling plus a customer switcher in the header for live customer-scoped queries.

Current wiring:

- Login/session state uses `/api/login`, `/api/session`, `/api/logout`, and `/api/session/customer`.
- The risk queue, telemetry trend, anomaly feed, and question panel call `/api/nl-query`.
- Batch drill-down calls `/api/batches/{batchId}`.
- Anomaly acknowledgment calls `/api/anomalies/{eventId}/ack`.
- Model performance calls `/api/model-performance`.
- Route map data calls `/api/routes/overview`.
- Threshold/alert settings call `/api/customer-settings`.
- Retraining controls call `/api/model-training`.
- The dashboard reads live PostgreSQL-backed data through the Functions app.
- The active customer is resolved from the authenticated session rather than a query parameter.

## Local Development

```bash
cd dashboard
npm install
npm run dev -- --port 5173
```

Open `http://localhost:5173`.

Demo credentials:

- `admin@perishguard.local`
- `ops+c010@perishguard.local`
- Password: `perishguard-demo`

## Production Build

```bash
cd dashboard
npm run build
```

## Docker

The dashboard Docker image builds the Vite app and serves it with Nginx.

```bash
docker compose build dashboard
docker compose up -d dashboard
```

Open `http://localhost:8081`.

Nginx proxies `/api/*` to the Functions container, so the dashboard can reach `/api/login`, `/api/session`, `/api/logout`, `/api/session/customer`, `/api/nl-query`, `/api/batches/{batchId}`, `/api/anomalies/{eventId}/ack`, `/api/model-performance`, `/api/routes/overview`, `/api/customer-settings`, `/api/model-training`, `/api/ingest-reading`, and `/api/run-analytics` when the full compose stack is running.
