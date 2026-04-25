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

## Platform Note

The Functions service is pinned to `linux/amd64`. PostgreSQL 16 Alpine, Azurite, dashboard, and training services follow the current Compose stack.

## Configure

```bash
cp .env.example .env
```

Defaults:

- `DISABLE_IOT_TRIGGER=true`, so the Functions app can start locally without live IoT Hub settings.
- `OLLAMA_ENDPOINT` and `NEMOCLAW_ENDPOINT` are blank, so deterministic fallbacks are used.
- PostgreSQL uses the local credentials from `.env`.

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

The dashboard proxies `/api/*` to the Functions container. For example, `/api/nl-query` is forwarded to the `nl_query` HTTP Function.

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
IOT_HUB_CONSUMER_GROUP=$Default
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

## Stop

```bash
docker compose down
```

Remove volumes:

```bash
docker compose down -v
```
