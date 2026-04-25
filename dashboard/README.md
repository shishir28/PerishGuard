# Dashboard

The dashboard is a React + Vite + Recharts operations view for PerishGuard.

## Features

- Risk queue for active batches.
- Temperature and risk trend chart.
- Live anomaly feed.
- Weekly business insights.
- Natural-language question panel that calls `/api/nl-query`.

Current wiring:

- The natural-language panel is live and proxies to the `nl_query` Azure Function.
- The risk queue, telemetry trend, anomaly feed, and weekly insights still render local fallback data defined in `src/main.jsx`.
- The current customer context is hard-coded to `C010` in the UI.

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

Nginx proxies `/api/*` to the Functions container, so `/api/nl-query` reaches the `nl_query` HTTP Function when the full compose stack is running.
