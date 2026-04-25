# model_performance

HTTP Function at `GET /api/model-performance?customerId=<id>`.

Returns customer-scoped model trust data built from:

- `vw_ModelPredictionTruth` for latest prediction vs `WasSpoiled`
- `vw_ModelPerformanceSummary` for grouped accuracy and error metrics

Payload sections:

- `overview`
- `productBreakdown`
- `recentBatches`
