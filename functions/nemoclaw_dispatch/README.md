# nemoclaw_dispatch

Task 3 multi-agent alert dispatch.

`predict_spoilage` calls this package after writing a prediction row. Dispatch runs only when alert routing rules match and the batch is outside cooldown.

## Agent Routing

| Agent | Trigger | Action |
|---|---|---|
| Logistics | `CRITICAL` risk and less than 12 hours left | Reroute, expedite, or find cold storage |
| Quality | `HIGH` or `CRITICAL` risk | Inspection and compliance note |
| Notify | `MEDIUM`, `HIGH`, or `CRITICAL` risk | Dashboard, email, and SMS notification copy |

## Runtime Behavior

1. Build alert context from batch, prediction, and current anomalies.
2. Generate alert copy with Ollama `POST /api/generate` when `OLLAMA_ENDPOINT` is configured.
3. Create NemoClaw tasks with `POST /api/v1/tasks` when `NEMOCLAW_ENDPOINT` is configured.
4. Mark prediction alert metadata in `"SpoilagePredictions"`.
5. Fall back to deterministic template text and task metadata when endpoints are unset or unavailable.

## Settings

- `OLLAMA_ENDPOINT`
- `OLLAMA_MODEL`
- `NEMOCLAW_ENDPOINT`
- `ALERT_COOLDOWN_MINUTES`
