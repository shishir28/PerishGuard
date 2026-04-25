"""Feature engineering: aggregate per-batch sensor history into the 24-feature
vector consumed by the spoilage classifier and shelf-life regressor.

Used for both training (full history per batch) and inference (rolling window
up to the current timestamp — the Azure Function reuses this module).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import (
    COLD_CHAIN_BREAK_MIN_MINUTES,
    FEATURE_COLUMNS,
    GAS_REFERENCE,
    PRODUCT_CONFIG,
    READING_INTERVAL_MINUTES,
)


def _count_cold_chain_breaks(temps: np.ndarray, safe_temp: float) -> int:
    """Count contiguous excursions (temp > safe_temp) lasting at least
    COLD_CHAIN_BREAK_MIN_MINUTES."""
    min_readings = max(COLD_CHAIN_BREAK_MIN_MINUTES // READING_INTERVAL_MINUTES, 1)
    above = temps > safe_temp
    if not above.any():
        return 0
    breaks = 0
    run = 0
    for flag in above:
        if flag:
            run += 1
        else:
            if run >= min_readings:
                breaks += 1
            run = 0
    if run >= min_readings:
        breaks += 1
    return breaks


def _gas_severity(row_max: dict[str, float]) -> float:
    """Normalised composite of the four gas channels (0..~4 range)."""
    return sum(row_max[k] / GAS_REFERENCE[k] for k in ("ethylene", "co2", "nh3", "voc"))


def features_for_batch(readings: pd.DataFrame, product_type: str) -> dict:
    """readings: DataFrame for one batch ordered by ReadingAt."""
    cfg = PRODUCT_CONFIG[product_type]
    temps = readings["Temperature"].to_numpy()
    humid = readings["Humidity"].to_numpy()

    # Temporal span — observation hours from first to last reading.
    times = pd.to_datetime(readings["ReadingAt"], utc=True)
    observation_hours = max((times.iloc[-1] - times.iloc[0]).total_seconds() / 3600, 1e-6)

    avg_temp = float(np.mean(temps))
    avg_humidity = float(np.mean(humid))
    max_eth = float(readings["Ethylene"].max())
    max_co2 = float(readings["CO2"].max())
    max_nh3 = float(readings["NH3"].max())
    max_voc = float(readings["VOC"].max())

    return {
        "avg_temp":                avg_temp,
        "max_temp":                float(np.max(temps)),
        "min_temp":                float(np.min(temps)),
        "std_temp":                float(np.std(temps)),
        "range_temp":              float(np.ptp(temps)),
        "avg_humidity":            avg_humidity,
        "max_humidity":            float(np.max(humid)),
        "avg_ethylene":            float(readings["Ethylene"].mean()),
        "max_ethylene":            max_eth,
        "avg_co2":                 float(readings["CO2"].mean()),
        "max_co2":                 max_co2,
        "avg_nh3":                 float(readings["NH3"].mean()),
        "max_nh3":                 max_nh3,
        "avg_voc":                 float(readings["VOC"].mean()),
        "max_voc":                 max_voc,
        "reading_count":           float(len(readings)),
        "observation_hours":       float(observation_hours),
        "cold_chain_break_count":  float(_count_cold_chain_breaks(temps, cfg["safe_temp"])),
        "temp_exceedance":         avg_temp - cfg["safe_temp"],
        "humidity_temp_interact":  avg_humidity * avg_temp,
        "gas_severity_index":      _gas_severity({"ethylene": max_eth, "co2": max_co2, "nh3": max_nh3, "voc": max_voc}),
        "reading_density":         float(len(readings)) / observation_hours,
        "product_code":            float(cfg["code"]),
        "expected_shelf_life_h":   float(cfg["shelf_hours"]),
    }


def build_feature_matrix(labels: pd.DataFrame, readings: pd.DataFrame) -> pd.DataFrame:
    """One row per labelled batch, columns = FEATURE_COLUMNS + label columns."""
    readings = readings.sort_values(["BatchId", "ReadingAt"])
    rows = []
    for batch_id, group in readings.groupby("BatchId", sort=False):
        label_row = labels.loc[labels["BatchId"] == batch_id]
        if label_row.empty:
            continue
        label_row = label_row.iloc[0]
        feats = features_for_batch(group, label_row["ProductType"])
        feats["BatchId"] = batch_id
        feats["WasSpoiled"] = int(label_row["WasSpoiled"])

        # Target for the regressor: actual hours the batch lasted.
        packaged = pd.to_datetime(label_row["PackagedAt"])
        end = pd.to_datetime(label_row["ActualSpoilageAt"]) if pd.notna(label_row["ActualSpoilageAt"]) else pd.to_datetime(label_row["ExpiresAt"])
        feats["ActualShelfLifeH"] = (end - packaged).total_seconds() / 3600
        rows.append(feats)

    df = pd.DataFrame(rows)
    # Ensure column order matches FEATURE_COLUMNS exactly.
    return df[["BatchId", *FEATURE_COLUMNS, "WasSpoiled", "ActualShelfLifeH"]]
