# model_training

`GET /api/model-training`

Returns recent retraining runs relevant to the current session.

`POST /api/model-training`

Runs synchronous retraining from PostgreSQL labels and readings, writes fresh
ONNX artifacts into `training/models`, and records the run history in
`ModelTrainingRuns`.
