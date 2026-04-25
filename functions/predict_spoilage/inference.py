"""Runtime inference support for the predict_spoilage Azure Function."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import pandas as pd

try:
    import psycopg
except ModuleNotFoundError:
    psycopg = None


def _find_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "training").is_dir():
            return parent
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _find_project_root()
TRAINING_DIR = PROJECT_ROOT / "training"
if str(TRAINING_DIR) not in sys.path:
    sys.path.insert(0, str(TRAINING_DIR))

from config import FEATURE_COLUMNS, MODEL_DIR as DEFAULT_MODEL_DIR, MODEL_VERSION, RISK_THRESHOLDS
from features import features_for_batch
try:
    from functions.anomaly_detection.detector import AnomalyEvent, detect_anomalies
    from functions.nemoclaw_dispatch.dispatcher import (
        AlertDispatcher,
        DispatchResult,
        agent_tasks_for_prediction,
        build_alert_context,
    )
except ModuleNotFoundError:
    from anomaly_detection.detector import AnomalyEvent, detect_anomalies
    from nemoclaw_dispatch.dispatcher import (
        AlertDispatcher,
        DispatchResult,
        agent_tasks_for_prediction,
        build_alert_context,
    )


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


@dataclass(frozen=True)
class PredictionResult:
    batch_id: str
    customer_id: str
    device_id: str
    product_type: str
    model_version: str
    spoilage_probability: float
    risk_level: str
    estimated_hours_left: float
    confidence_score: float
    cold_chain_breaks: int
    anomaly_count: int = 0
    critical_anomaly_count: int = 0


@dataclass(frozen=True)
class StoredPrediction:
    prediction_id: int
    result: PredictionResult


class OnnxBundle:
    def __init__(self, model_dir: Path) -> None:
        metadata_path = model_dir / "model_metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"{metadata_path} not found. Run training/train_spoilage_model.py first.")

        self.metadata = json.loads(metadata_path.read_text())
        self.model_version = self.metadata.get("model_version", MODEL_VERSION)
        self.feature_columns = self.metadata.get("feature_columns", FEATURE_COLUMNS)
        self.risk_thresholds = self.metadata.get("risk_thresholds", RISK_THRESHOLDS)

        artefacts = self.metadata.get("artefacts", {})
        classifier_path = model_dir / artefacts.get("classifier_onnx", "spoilage_classifier.onnx")
        regressor_path = model_dir / artefacts.get("regressor_onnx", "shelf_life_regressor.onnx")

        self.classifier = ort.InferenceSession(str(classifier_path), providers=["CPUExecutionProvider"])
        self.regressor = ort.InferenceSession(str(regressor_path), providers=["CPUExecutionProvider"])
        self.classifier_input = self.classifier.get_inputs()[0].name
        self.regressor_input = self.regressor.get_inputs()[0].name

    def predict(self, features: dict[str, float]) -> tuple[float, float]:
        x = np.array([[features[name] for name in self.feature_columns]], dtype=np.float32)

        cls_outputs = self.classifier.run(None, {self.classifier_input: x})
        probability = _extract_positive_probability(cls_outputs)
        hours_left = float(np.ravel(self.regressor.run(None, {self.regressor_input: x})[0])[0])
        return probability, max(hours_left, 0.0)


class PredictionService:
    def __init__(
        self,
        connection_string: str,
        model_dir: Path,
        alert_dispatcher: AlertDispatcher | None = None,
    ) -> None:
        self.connection_string = connection_string
        self.models = OnnxBundle(model_dir)
        self.alert_dispatcher = alert_dispatcher or AlertDispatcher.from_environment()

    @classmethod
    def from_environment(cls) -> "PredictionService":
        connection_string = os.environ["SQL_CONNECTION_STRING"]
        model_dir = Path(os.getenv("MODEL_DIR", str(DEFAULT_MODEL_DIR))).expanduser()
        if not model_dir.is_absolute():
            model_dir = (PROJECT_ROOT / model_dir).resolve()
        return cls(connection_string=connection_string, model_dir=model_dir)

    def process_reading(self, payload: dict[str, Any]) -> PredictionResult:
        if psycopg is None:
            raise RuntimeError("psycopg is required for Postgres access. Install functions/requirements.txt.")

        reading = normalize_reading(payload)

        with psycopg.connect(self.connection_string, autocommit=False) as conn:
            insert_sensor_reading(conn, reading)
            history = load_batch_readings(conn, reading["BatchId"])
            anomalies = detect_anomalies(reading, history)
            insert_anomaly_events(conn, anomalies)
            result = self.predict_from_history(reading, history, anomalies)
            stored = insert_prediction(conn, result, history)
            dispatch_result = maybe_dispatch_alerts(conn, self.alert_dispatcher, stored.result, anomalies)
            if dispatch_result.alert_sent:
                mark_alert_sent(conn, stored.prediction_id, dispatch_result.channel)
            conn.commit()
            return result

    def predict_from_history(
        self,
        reading: dict[str, Any],
        history: pd.DataFrame,
        anomalies: list[AnomalyEvent] | None = None,
    ) -> PredictionResult:
        if history.empty:
            raise ValueError(f"No sensor history found for batch {reading['BatchId']}")

        anomalies = anomalies or []
        product_type = str(reading["ProductType"]).lower()
        features = features_for_batch(history, product_type)
        probability, hours_left = self.models.predict(features)
        risk_level = risk_from_probability(probability, self.models.risk_thresholds)
        critical_anomaly_count = sum(1 for event in anomalies if event.severity == "CRITICAL")
        anomaly_breaks = sum(
            1
            for event in anomalies
            if event.sensor_type == "temperature" and event.anomaly_type in ("threshold", "rate_of_change")
        )

        return PredictionResult(
            batch_id=reading["BatchId"],
            customer_id=reading["CustomerId"],
            device_id=reading["DeviceId"],
            product_type=product_type,
            model_version=self.models.model_version,
            spoilage_probability=probability,
            risk_level=risk_level,
            estimated_hours_left=hours_left,
            confidence_score=confidence_from_probability(probability),
            cold_chain_breaks=int(features["cold_chain_break_count"]) + anomaly_breaks,
            anomaly_count=len(anomalies),
            critical_anomaly_count=critical_anomaly_count,
        )


def normalize_reading(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "BatchId": payload.get("BatchId") or payload.get("batchId"),
        "CustomerId": payload.get("CustomerId") or payload.get("customerId"),
        "DeviceId": payload.get("DeviceId") or payload.get("deviceId"),
        "ProductType": (payload.get("ProductType") or payload.get("productType") or "").lower(),
        "ReadingAt": payload.get("ReadingAt") or payload.get("readingAt") or utc_now_iso(),
        "Temperature": payload.get("Temperature") if "Temperature" in payload else payload.get("temperature"),
        "Humidity": payload.get("Humidity") if "Humidity" in payload else payload.get("humidity"),
        "Ethylene": payload.get("Ethylene") if "Ethylene" in payload else payload.get("ethylene", 0.0),
        "CO2": payload.get("CO2") if "CO2" in payload else payload.get("co2", 0.0),
        "NH3": payload.get("NH3") if "NH3" in payload else payload.get("nh3", 0.0),
        "VOC": payload.get("VOC") if "VOC" in payload else payload.get("voc", 0.0),
        "ShockG": payload.get("ShockG") if "ShockG" in payload else payload.get("shockG", 0.0),
        "LightLux": payload.get("LightLux") if "LightLux" in payload else payload.get("lightLux", 0.0),
    }

    missing = [
        key
        for key in ("BatchId", "CustomerId", "DeviceId", "ProductType", "Temperature", "Humidity")
        if normalized[key] in (None, "")
    ]
    if missing:
        raise ValueError(f"Missing required telemetry field(s): {', '.join(missing)}")

    normalized["ReadingAt"] = normalize_timestamp(normalized["ReadingAt"])

    for key in ("Temperature", "Humidity", "Ethylene", "CO2", "NH3", "VOC", "ShockG", "LightLux"):
        normalized[key] = float(normalized[key])

    return normalized


def normalize_timestamp(value: Any) -> str:
    timestamp = pd.to_datetime(value, utc=True)
    return timestamp.tz_localize(None).isoformat(timespec="seconds")


def insert_sensor_reading(conn: "psycopg.Connection", reading: dict[str, Any]) -> None:
    values = [reading[column] for column in READING_COLUMNS]
    placeholders = ", ".join("%s" for _ in READING_COLUMNS)
    columns = ", ".join(f'"{c}"' for c in READING_COLUMNS)
    conn.execute(f'INSERT INTO "SensorReadings" ({columns}) VALUES ({placeholders})', values)


def load_batch_readings(conn: "psycopg.Connection", batch_id: str) -> pd.DataFrame:
    query = """
        SELECT "BatchId", "CustomerId", "DeviceId", "ProductType", "ReadingAt",
               "Temperature", "Humidity", "Ethylene", "CO2", "NH3", "VOC",
               "ShockG", "LightLux"
        FROM "SensorReadings"
        WHERE "BatchId" = %s
        ORDER BY "ReadingAt"
    """
    with conn.cursor() as cur:
        cur.execute(query, [batch_id])
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=columns)


def insert_anomaly_events(conn: "psycopg.Connection", anomalies: list[AnomalyEvent]) -> None:
    if not anomalies:
        return

    for anomaly in anomalies:
        conn.execute(
            """
            INSERT INTO "AnomalyEvents" (
                "BatchId", "CustomerId", "DeviceId", "SensorType", "ReadingValue",
                "BaselineMean", "BaselineStd", "DeviationScore", "AnomalyType", "Severity"
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                anomaly.batch_id,
                anomaly.customer_id,
                anomaly.device_id,
                anomaly.sensor_type,
                anomaly.reading_value,
                anomaly.baseline_mean,
                anomaly.baseline_std,
                anomaly.deviation_score,
                anomaly.anomaly_type,
                anomaly.severity,
            ),
        )


def insert_prediction(conn: "psycopg.Connection", result: PredictionResult, history: pd.DataFrame) -> StoredPrediction:
    history = history.copy()
    history["ReadingAt"] = pd.to_datetime(history["ReadingAt"], utc=True)
    latest = history["ReadingAt"].max()
    last_hour = history[history["ReadingAt"] >= latest - pd.Timedelta(hours=1)]
    last_day = history[history["ReadingAt"] >= latest - pd.Timedelta(hours=24)]

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO "SpoilagePredictions" (
                "BatchId", "CustomerId", "DeviceId", "ProductType", "ModelVersion",
                "SpoilageProbability", "EstimatedHoursLeft", "ConfidenceScore",
                "AvgTempLast1h", "MaxTempLast1h", "TempVariance24h", "ColdChainBreaks"
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING "PredictionId"
            """,
            (
                result.batch_id,
                result.customer_id,
                result.device_id,
                result.product_type,
                result.model_version,
                result.spoilage_probability,
                result.estimated_hours_left,
                result.confidence_score,
                float(last_hour["Temperature"].mean()),
                float(last_hour["Temperature"].max()),
                float(last_day["Temperature"].var(ddof=0)),
                result.cold_chain_breaks,
            ),
        )
        prediction_id = int(cur.fetchone()[0])
    return StoredPrediction(prediction_id=prediction_id, result=result)


def maybe_dispatch_alerts(
    conn: "psycopg.Connection",
    dispatcher: AlertDispatcher,
    result: PredictionResult,
    anomalies: list[AnomalyEvent],
) -> DispatchResult:
    context = build_alert_context(result, anomalies)
    if not agent_tasks_for_prediction(context):
        return DispatchResult(False, False, None, None, [])
    if alert_in_cooldown(conn, result.batch_id, dispatcher.cooldown_minutes):
        return DispatchResult(True, False, "cooldown", None, [])
    return dispatcher.dispatch(context)


def alert_in_cooldown(conn: "psycopg.Connection", batch_id: str, cooldown_minutes: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT "AlertSentAt"
            FROM "SpoilagePredictions"
            WHERE "BatchId" = %s AND "AlertSent" = 1 AND "AlertSentAt" IS NOT NULL
            ORDER BY "AlertSentAt" DESC
            LIMIT 1
            """,
            (batch_id,),
        )
        row = cur.fetchone()
    if row is None or row[0] is None:
        return False

    sent_at = pd.to_datetime(row[0], utc=True)
    now = pd.Timestamp.now("UTC")
    return (now - sent_at) < pd.Timedelta(minutes=cooldown_minutes)


def mark_alert_sent(conn: "psycopg.Connection", prediction_id: int, channel: str | None) -> None:
    conn.execute(
        """
        UPDATE "SpoilagePredictions"
        SET "AlertSent" = 1,
            "AlertSentAt" = (now() AT TIME ZONE 'utc'),
            "AlertChannel" = %s
        WHERE "PredictionId" = %s
        """,
        (channel or "unknown", prediction_id),
    )


def risk_from_probability(probability: float, thresholds: dict[str, float]) -> str:
    if probability >= thresholds["CRITICAL"]:
        return "CRITICAL"
    if probability >= thresholds["HIGH"]:
        return "HIGH"
    if probability >= thresholds["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


def confidence_from_probability(probability: float) -> float:
    return round(abs(probability - 0.5) * 2, 4)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _extract_positive_probability(outputs: list[Any]) -> float:
    for output in outputs:
        arr = np.asarray(output)
        if arr.ndim == 2 and arr.shape[1] >= 2:
            return float(arr[0, 1])
        if arr.ndim == 1 and arr.size >= 2:
            return float(arr[1])
    arr = np.asarray(outputs[-1])
    return float(np.ravel(arr)[-1])
