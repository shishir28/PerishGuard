"""Retraining support using PostgreSQL labels and readings."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import psycopg
except ModuleNotFoundError:
    psycopg = None


def _find_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "training").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = _find_project_root()
TRAINING_DIR = PROJECT_ROOT / "training"
if str(TRAINING_DIR) not in sys.path:
    sys.path.insert(0, str(TRAINING_DIR))

from config import MODEL_DIR as DEFAULT_MODEL_DIR
from train_spoilage_model import build_training_frame, train_and_export


LABEL_COLUMNS = [
    "BatchId",
    "CustomerId",
    "ProductType",
    "Origin",
    "Destination",
    "Carrier",
    "PackagingType",
    "SupplierId",
    "PackagedAt",
    "ExpiresAt",
    "ActualSpoilageAt",
    "WasSpoiled",
    "SpoilageType",
    "QualityScore",
]

READING_COLUMNS = [
    "BatchId",
    "CustomerId",
    "DeviceId",
    "ProductType",
    "ReadingAt",
    "Temperature",
    "Humidity",
    "Ethylene",
    "CO2",
    "NH3",
    "VOC",
    "ShockG",
    "LightLux",
]


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError("psycopg is required for Postgres access. Install functions/requirements.txt.")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class ModelTrainingService:
    def __init__(self, connection_string: str, model_dir: Path) -> None:
        self.connection_string = connection_string
        self.model_dir = model_dir

    @classmethod
    def from_environment(cls) -> "ModelTrainingService":
        model_dir = Path(os.getenv("MODEL_DIR", str(DEFAULT_MODEL_DIR))).expanduser()
        if not model_dir.is_absolute():
            model_dir = (PROJECT_ROOT / model_dir).resolve()
        return cls(os.environ["SQL_CONNECTION_STRING"], model_dir)

    def retrain(self, requested_by_user_id: str, customer_id: str | None = None, scope: str = "global") -> dict[str, Any]:
        _require_psycopg()
        scope = scope.strip().lower() or "global"
        if scope not in {"global", "customer"}:
            raise ValueError("scope must be 'global' or 'customer'")
        if scope == "customer" and not customer_id:
            raise ValueError("customer-scoped retraining requires a customer")

        run_id = self._insert_run(requested_by_user_id, customer_id if scope == "customer" else None)
        try:
            labels, readings = self._load_training_data(customer_id if scope == "customer" else None)
            df = build_training_frame(labels, readings)
            version_suffix = _utc_now().strftime("%Y%m%d%H%M%S")
            model_version = f"v1.0.0+rt{version_suffix}"
            metrics = train_and_export(
                df,
                model_dir=self.model_dir,
                model_version=model_version,
                metadata_extra={
                    "training_scope": scope,
                    "training_customer_id": customer_id if scope == "customer" else None,
                    "requested_by_user_id": requested_by_user_id,
                },
            )
            metrics["labelCount"] = int(len(labels))
            metrics["readingCount"] = int(len(readings))
            metrics["scope"] = scope
            metrics["customerId"] = customer_id if scope == "customer" else None
            self._finish_run(run_id, "succeeded", metrics, model_version, None)
            return {
                "runId": run_id,
                "status": "succeeded",
                "modelVersion": model_version,
                "metrics": metrics,
            }
        except Exception as exc:
            self._finish_run(run_id, "failed", None, None, str(exc))
            raise

    def _insert_run(self, requested_by_user_id: str, customer_id: str | None) -> int:
        with psycopg.connect(self.connection_string, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT COUNT(*) FROM "ModelTrainingRuns" WHERE "Status" = %s',
                    ("running",),
                )
                if int(cur.fetchone()[0]) > 0:
                    raise ValueError("A retraining run is already in progress")
                cur.execute(
                    """
                    INSERT INTO "ModelTrainingRuns" (
                        "RequestedByUserId", "CustomerId", "Status", "StartedAt", "OutputDir"
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING "RunId"
                    """,
                    (requested_by_user_id, customer_id, "running", _utc_now(), str(self.model_dir)),
                )
                run_id = int(cur.fetchone()[0])
            conn.commit()
        return run_id

    def _finish_run(
        self,
        run_id: int,
        status: str,
        metrics: dict[str, Any] | None,
        model_version: str | None,
        error_message: str | None,
    ) -> None:
        with psycopg.connect(self.connection_string, autocommit=False) as conn:
            conn.execute(
                """
                UPDATE "ModelTrainingRuns"
                SET
                    "Status" = %s,
                    "CompletedAt" = %s,
                    "TrainingMetrics" = %s::jsonb,
                    "ModelVersion" = %s,
                    "ErrorMessage" = %s
                WHERE "RunId" = %s
                """,
                (
                    status,
                    _utc_now(),
                    json.dumps(metrics) if metrics is not None else None,
                    model_version,
                    error_message,
                    run_id,
                ),
            )
            conn.commit()

    def _load_training_data(self, customer_id: str | None) -> tuple[pd.DataFrame, pd.DataFrame]:
        label_columns = ", ".join(f'"{col}"' for col in LABEL_COLUMNS)
        reading_columns = ", ".join(f'"{col}"' for col in READING_COLUMNS)
        label_query = f'SELECT {label_columns} FROM "SpoilageLabels"'
        reading_query = f'SELECT {reading_columns} FROM "SensorReadings"'
        params: tuple[Any, ...] = ()
        if customer_id:
            label_query += ' WHERE "CustomerId" = %s'
            reading_query += ' WHERE "CustomerId" = %s'
            params = (customer_id,)
        label_query += ' ORDER BY "BatchId"'
        reading_query += ' ORDER BY "BatchId", "ReadingAt"'

        with psycopg.connect(self.connection_string, autocommit=True) as conn:
            labels = self._read_frame(conn, label_query, params)
            readings = self._read_frame(conn, reading_query, params)
        return labels, readings

    @staticmethod
    def _read_frame(
        conn: "psycopg.Connection[Any]",
        query: str,
        params: tuple[Any, ...],
    ) -> pd.DataFrame:
        with conn.cursor() as cur:
            cur.execute(query, params)
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
        return pd.DataFrame(rows, columns=columns)
