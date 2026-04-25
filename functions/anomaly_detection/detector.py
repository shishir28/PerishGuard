"""Real-time per-reading anomaly detection for PerishGuard.

The detector is intentionally deterministic and fast so it can run in the IoT
ingestion path before ONNX spoilage prediction.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAINING_DIR = PROJECT_ROOT / "training"
if str(TRAINING_DIR) not in sys.path:
    sys.path.insert(0, str(TRAINING_DIR))

from config import GAS_REFERENCE, PRODUCT_CONFIG


ROLLING_HOURS = 24
STATISTICAL_SIGMA = 3.0
MIN_BASELINE_READINGS = 12
RATE_WINDOW_MINUTES = 30
TEMP_RATE_DELTA_C = 2.0

SENSOR_COLUMNS = {
    "temperature": "Temperature",
    "humidity": "Humidity",
    "ethylene": "Ethylene",
    "co2": "CO2",
    "nh3": "NH3",
    "voc": "VOC",
}


@dataclass(frozen=True)
class AnomalyEvent:
    batch_id: str
    customer_id: str
    device_id: str
    sensor_type: str
    reading_value: float
    baseline_mean: float | None
    baseline_std: float | None
    deviation_score: float | None
    anomaly_type: str
    severity: str


def detect_anomalies(reading: dict[str, Any], history: pd.DataFrame) -> list[AnomalyEvent]:
    """Return all anomaly events for the latest reading.

    `history` should include the latest reading and be ordered by ReadingAt.
    The statistical baseline excludes the latest reading to avoid diluting the
    anomaly being evaluated.
    """
    if history.empty:
        return []

    history = history.copy()
    history["ReadingAt"] = pd.to_datetime(history["ReadingAt"], utc=True)
    current_at = pd.to_datetime(reading["ReadingAt"], utc=True)
    baseline = history[history["ReadingAt"] < current_at]
    rolling = baseline[baseline["ReadingAt"] >= current_at - pd.Timedelta(hours=ROLLING_HOURS)]

    events: list[AnomalyEvent] = []
    events.extend(_threshold_anomalies(reading))
    events.extend(_statistical_anomalies(reading, rolling))
    rate_event = _rate_of_change_anomaly(reading, baseline)
    if rate_event is not None:
        events.append(rate_event)
    events.extend(_binary_trigger_anomalies(reading))
    return _dedupe(events)


def _threshold_anomalies(reading: dict[str, Any]) -> list[AnomalyEvent]:
    events: list[AnomalyEvent] = []
    product_type = str(reading["ProductType"]).lower()
    cfg = PRODUCT_CONFIG[product_type]

    temp = float(reading["Temperature"])
    safe_temp = cfg["safe_temp"]
    if temp > safe_temp:
        events.append(_event(reading, "temperature", temp, None, None, None, "threshold", _temp_severity(temp - safe_temp)))

    humidity = float(reading["Humidity"])
    if humidity >= 90.0:
        events.append(_event(reading, "humidity", humidity, None, None, None, "threshold", "CRITICAL"))
    elif humidity >= 85.0:
        events.append(_event(reading, "humidity", humidity, None, None, None, "threshold", "WARNING"))

    gas_limits = {
        "ethylene": GAS_REFERENCE["ethylene"],
        "co2": GAS_REFERENCE["co2"],
        "nh3": GAS_REFERENCE["nh3"],
        "voc": GAS_REFERENCE["voc"],
    }
    for sensor, limit in gas_limits.items():
        column = SENSOR_COLUMNS[sensor]
        value = float(reading[column])
        if value >= limit:
            severity = "CRITICAL" if value >= limit * 1.5 else "WARNING"
            events.append(_event(reading, sensor, value, None, None, None, "threshold", severity))

    return events


def _statistical_anomalies(reading: dict[str, Any], rolling: pd.DataFrame) -> list[AnomalyEvent]:
    if len(rolling) < MIN_BASELINE_READINGS:
        return []

    events: list[AnomalyEvent] = []
    for sensor, column in SENSOR_COLUMNS.items():
        values = pd.to_numeric(rolling[column], errors="coerce").dropna()
        if len(values) < MIN_BASELINE_READINGS:
            continue
        mean = float(values.mean())
        std = float(values.std(ddof=0))
        if std <= 0:
            continue

        current = float(reading[column])
        deviation = abs(current - mean) / std
        if deviation >= STATISTICAL_SIGMA:
            severity = "CRITICAL" if deviation >= STATISTICAL_SIGMA * 1.5 else "WARNING"
            events.append(_event(reading, sensor, current, mean, std, deviation, "statistical", severity))

    return events


def _rate_of_change_anomaly(reading: dict[str, Any], baseline: pd.DataFrame) -> AnomalyEvent | None:
    if baseline.empty:
        return None

    current_at = pd.to_datetime(reading["ReadingAt"], utc=True)
    window_start = current_at - pd.Timedelta(minutes=RATE_WINDOW_MINUTES)
    prior = baseline[baseline["ReadingAt"] >= window_start]
    if prior.empty:
        prior = baseline.tail(1)

    previous_temp = float(prior.iloc[0]["Temperature"])
    current_temp = float(reading["Temperature"])
    delta = current_temp - previous_temp
    if delta <= TEMP_RATE_DELTA_C:
        return None

    severity = "CRITICAL" if delta >= TEMP_RATE_DELTA_C * 2 else "WARNING"
    return _event(reading, "temperature", current_temp, previous_temp, None, delta, "rate_of_change", severity)


def _binary_trigger_anomalies(reading: dict[str, Any]) -> list[AnomalyEvent]:
    events: list[AnomalyEvent] = []

    shock = float(reading.get("ShockG", 0.0) or 0.0)
    if shock >= 2.5:
        events.append(_event(reading, "shock", shock, None, None, None, "shock", "CRITICAL" if shock >= 5.0 else "WARNING"))

    light = float(reading.get("LightLux", 0.0) or 0.0)
    if light >= 200.0:
        events.append(_event(reading, "light", light, None, None, None, "light", "CRITICAL" if light >= 1000.0 else "WARNING"))

    return events


def _event(
    reading: dict[str, Any],
    sensor_type: str,
    reading_value: float,
    baseline_mean: float | None,
    baseline_std: float | None,
    deviation_score: float | None,
    anomaly_type: str,
    severity: str,
) -> AnomalyEvent:
    return AnomalyEvent(
        batch_id=str(reading["BatchId"]),
        customer_id=str(reading["CustomerId"]),
        device_id=str(reading["DeviceId"]),
        sensor_type=sensor_type,
        reading_value=float(reading_value),
        baseline_mean=baseline_mean,
        baseline_std=baseline_std,
        deviation_score=deviation_score,
        anomaly_type=anomaly_type,
        severity=severity,
    )


def _temp_severity(delta_c: float) -> str:
    if delta_c >= 4.0:
        return "CRITICAL"
    return "WARNING"


def _dedupe(events: list[AnomalyEvent]) -> list[AnomalyEvent]:
    seen: set[tuple[str, str]] = set()
    unique: list[AnomalyEvent] = []
    for event in sorted(events, key=lambda e: _severity_rank(e.severity), reverse=True):
        key = (event.sensor_type, event.anomaly_type)
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def _severity_rank(severity: str) -> int:
    return {"CRITICAL": 3, "WARNING": 2, "INFO": 1}.get(severity, 0)
