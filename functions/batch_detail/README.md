# batch_detail

HTTP Function at `GET /api/batches/{batchId}?customerId=<id>`.

Returns customer-scoped drill-down data for a selected batch:

- `summary`: latest row from `vw_BatchRiskSummary`
- `sensorHistory`: recent sensor readings
- `predictionHistory`: prediction-over-time for the batch
- `anomalies`: latest anomaly events
- `alertLog`: per-channel alert delivery history from `AlertDispatchLog`
