# Dashboard

The dashboard is a React + Vite + Recharts operations view for PerishGuard.

## Features

- Risk queue for active batches.
- Temperature trend chart.
- Live anomaly feed.
- Anomaly acknowledgment actions.
- Click-through batch drill-down with sensor history, prediction history, and alert log.
- Model performance panel comparing latest prediction vs observed spoilage outcomes.
- Natural-language question panel that calls `/api/nl-query`.
- Customer switcher in the header for live customer-scoped queries.

Current wiring:

- The risk queue, telemetry trend, anomaly feed, and question panel call `/api/nl-query`.
- Batch drill-down calls `/api/batches/{batchId}`.
- Anomaly acknowledgment calls `/api/anomalies/{eventId}/ack`.
- Model performance calls `/api/model-performance`.
- The dashboard reads live PostgreSQL-backed data through the Functions app.
- The initial customer comes from the `?customer=` query parameter when present, otherwise it defaults to `C010`.

## Local Development

```bash
cd dashboard
npm install
npm run dev -- --port 5173
```

Open `http://localhost:5173`.

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

Nginx proxies `/api/*` to the Functions container, so the dashboard can reach `/api/nl-query`, `/api/batches/{batchId}`, `/api/anomalies/{eventId}/ack`, `/api/model-performance`, `/api/ingest-reading`, and `/api/run-analytics` when the full compose stack is running.
