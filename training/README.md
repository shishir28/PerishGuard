# Training Pipeline

The training package generates local data, builds features, trains LightGBM models, exports ONNX artifacts, and writes metadata consumed by the `predict_spoilage` Function.

## Files

| File | Purpose |
|---|---|
| `config.py` | Product thresholds, risk bands, feature list, and artifact paths |
| `synthetic_data.py` | Synthetic batches and sensor readings with customer and business metadata |
| `seed_local_db.py` | Creates local SQLite schema and inserts synthetic data |
| `features.py` | Shared 24-feature engineering logic |
| `train_spoilage_model.py` | Cross-validation, model training, ONNX export, metadata |
| `Dockerfile` | Training utility image |

## Local Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r training/requirements.txt
```

## Run Locally

```bash
.venv/bin/python training/seed_local_db.py --batches 400
.venv/bin/python training/train_spoilage_model.py
```

Outputs:

- `training/models/spoilage_classifier.onnx`
- `training/models/shelf_life_regressor.onnx`
- `training/models/model_metadata.json`

These files are generated artifacts and ignored by Git.

## Run With Docker

```bash
docker compose --profile tools run --rm training
```

## Bootstrap PostgreSQL For Demos

After generating `perishguard.db`, copy its seeded labels and readings into the local Postgres stack:

```bash
docker compose up -d
docker compose --profile tools run --rm demo-tools python infra/seed_postgres_from_sqlite.py
```

To produce fresh live predictions and anomalies after the bootstrap:

```bash
docker compose --profile tools run --rm demo-tools \
  python infra/synthetic_generator.py --rate 5 --duration 60
```

## Data Model

The local SQLite database mirrors the application tables closely enough for training and smoke tests:

- `SensorReadings`
- `SpoilageLabels`
- `SpoilagePredictions`
- `AnomalyEvents`
- `AnalyticsReports`
- `vw_BatchRiskSummary`

The deployed application stack uses PostgreSQL, with canonical schema and view definitions in `sql/*.sql`. Training remains SQLite-based so model seeding and experimentation stay lightweight and self-contained.

## Current Validation

Latest local validation on synthetic data:

- Classifier ROC-AUC: `1.0000`
- Regressor MAE: about `1.34h`
- ONNX inference: below `0.05ms`

Synthetic results are intentionally clean and should be replaced or supplemented with QA inspection records before production rollout.
