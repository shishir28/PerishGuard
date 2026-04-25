"""Domain constants shared by synthetic data generation, feature engineering,
and training. Kept in one file so the values also flow into model_metadata.json."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "perishguard.db"
MODEL_DIR = PROJECT_ROOT / "training" / "models"

# Safe temperature ceilings (°C) — see IMPLEMENTATION_PLAN.md Task 1.
PRODUCT_CONFIG = {
    "dairy":   {"safe_temp": 4.0,  "base_temp": 3.0,  "shelf_hours": 168, "code": 0},
    "meat":    {"safe_temp": 2.0,  "base_temp": 1.0,  "shelf_hours": 120, "code": 1},
    "seafood": {"safe_temp": 0.0,  "base_temp": -1.0, "shelf_hours": 72,  "code": 2},
    "produce": {"safe_temp": 7.0,  "base_temp": 5.0,  "shelf_hours": 240, "code": 3},
    "bakery":  {"safe_temp": 21.0, "base_temp": 20.0, "shelf_hours": 168, "code": 4},
}

# Reference upper-bound values for normalising gas readings into the
# composite GasSeverityIndex feature.
GAS_REFERENCE = {
    "ethylene": 5.0,   # ppm
    "co2":      5000,  # ppm
    "nh3":      25.0,  # ppm
    "voc":      1000,  # ppb
}

READING_INTERVAL_MINUTES = 10
COLD_CHAIN_BREAK_MIN_MINUTES = 30  # excursion must last this long to count

RISK_THRESHOLDS = {
    "CRITICAL": 0.80,
    "HIGH":     0.60,
    "MEDIUM":   0.35,
}

MODEL_VERSION = "v1.0.0"

FEATURE_COLUMNS = [
    "avg_temp", "max_temp", "min_temp", "std_temp", "range_temp",
    "avg_humidity", "max_humidity",
    "avg_ethylene", "max_ethylene",
    "avg_co2", "max_co2",
    "avg_nh3", "max_nh3",
    "avg_voc", "max_voc",
    "reading_count", "observation_hours", "cold_chain_break_count",
    "temp_exceedance", "humidity_temp_interact", "gas_severity_index",
    "reading_density",
    "product_code", "expected_shelf_life_h",
]
