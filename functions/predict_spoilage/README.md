# predict_spoilage

Task 1 runtime inference Function plus Task 2 and Task 3 integration.

## Trigger

`eventHubTrigger` through the IoT Hub Event Hub-compatible endpoint.

For Docker/local HTTP-only work, this trigger is disabled by default through:

```text
AzureWebJobs.predict_spoilage.Disabled=true
```

## Flow

1. Decode telemetry JSON.
2. Normalize required fields: `CustomerId`, `BatchId`, `DeviceId`, `ProductType`, timestamp, temperature, humidity, gases, shock, and light.
3. Insert the reading into `"SensorReadings"`.
4. Run `anomaly_detection` and write `"AnomalyEvents"`.
5. Load ordered batch history.
6. Build the shared 24-feature vector from `training/features.py`.
7. Run `spoilage_classifier.onnx` and `shelf_life_regressor.onnx`.
8. Insert `"SpoilagePredictions"`.
9. Dispatch alerts through `nemoclaw_dispatch` when routing rules match and cooldown allows.

## Required Settings

- `SQL_CONNECTION_STRING` (PostgreSQL connection string used by `psycopg`)
- `MODEL_DIR`
- `IOT_HUB_CONNECTION`
- `IOT_HUB_EVENT_HUB_NAME`
- `IOT_HUB_CONSUMER_GROUP`

Optional alert settings:

- `OLLAMA_ENDPOINT`
- `OLLAMA_MODEL`
- `NEMOCLAW_ENDPOINT`
- `ALERT_COOLDOWN_MINUTES`

## Model Artifacts

`MODEL_DIR` must contain:

- `spoilage_classifier.onnx`
- `shelf_life_regressor.onnx`
- `model_metadata.json`

Generate them with:

```bash
.venv/bin/python training/seed_local_db.py --batches 400
.venv/bin/python training/train_spoilage_model.py
```
