# ingest_reading

HTTP shim around the `predict_spoilage` pipeline for local demos and synthetic traffic.

## Endpoint

```http
POST /api/ingest-reading
Content-Type: application/json
```

The request body uses the same telemetry payload shape as the Event Hub trigger:

- `CustomerId`
- `BatchId`
- `DeviceId`
- `ProductType`
- `ReadingAt`
- `Temperature`
- `Humidity`
- `Ethylene`
- `CO2`
- `NH3`
- `VOC`
- `ShockG`
- `LightLux`

## Behavior

- Validates the request body as JSON.
- Invokes the shared `PredictionService`.
- Inserts sensor readings, anomalies, and predictions into PostgreSQL.
- Triggers alert dispatch using the same cooldown and fallback behavior as `predict_spoilage`.

This endpoint is intended for local demos, synthetic traffic generation, and manual smoke tests when IoT Hub is not part of the stack.
