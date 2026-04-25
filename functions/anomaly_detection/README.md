# anomaly_detection

Task 2 real-time anomaly detection.

This package is called by `predict_spoilage` after a telemetry reading is stored and before ONNX prediction runs.

## Inputs

- Latest normalized telemetry reading.
- Ordered batch history including the latest reading.

## Methods

- Statistical: 3-sigma check against the previous 24 hours for temperature, humidity, ethylene, CO2, NH3, and VOC.
- Threshold: product-specific temperature ceilings plus humidity and gas limits.
- Rate-of-change: temperature rise greater than 2 C in 30 minutes.
- Binary triggers: shock and light exposure.

## Output

Detected events are represented as `AnomalyEvent` records and written to `"AnomalyEvents"` by `predict_spoilage`.

Fields include:

- `CustomerId`
- `BatchId`
- `DeviceId`
- `SensorType`
- `ReadingValue`
- `BaselineMean`
- `BaselineStd`
- `DeviationScore`
- `AnomalyType`
- `Severity`

Temperature threshold and rate-of-change anomalies also contribute to the prediction `ColdChainBreaks` snapshot.
