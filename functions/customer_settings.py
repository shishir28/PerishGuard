"""Customer-specific runtime settings with safe fallbacks."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

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

from config import RISK_THRESHOLDS

DEFAULT_ANOMALY_CONFIG = {
    "humidityWarning": 85.0,
    "humidityCritical": 90.0,
    "gasCriticalMultiplier": 1.5,
    "temperatureRateDelta": 2.0,
    "temperatureCriticalDelta": 4.0,
}


def _default_alert_config() -> dict[str, Any]:
    return {
        "cooldownMinutes": int(os.getenv("ALERT_COOLDOWN_MINUTES", "30")),
        "logisticsHoursLeftTrigger": 12,
        "emailEnabled": True,
        "slackEnabled": True,
    }


def default_settings() -> dict[str, Any]:
    return {
        "riskThresholds": dict(RISK_THRESHOLDS),
        "anomalyConfig": dict(DEFAULT_ANOMALY_CONFIG),
        "alertConfig": _default_alert_config(),
        "routeConfig": {},
    }


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError("psycopg is required for Postgres access. Install functions/requirements.txt.")


def _connect(connection_string: str) -> "psycopg.Connection[Any]":
    _require_psycopg()
    return psycopg.connect(connection_string, autocommit=False)


class CustomerSettingsService:
    def __init__(self, connection_string: str) -> None:
        self.connection_string = connection_string

    @classmethod
    def from_environment(cls) -> "CustomerSettingsService":
        return cls(os.environ["SQL_CONNECTION_STRING"])

    def get_settings(self, customer_id: str) -> dict[str, Any]:
        with _connect(self.connection_string) as conn:
            result = load_runtime_settings_from_connection(conn, customer_id)
            conn.commit()
            return result

    def update_settings(self, customer_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_settings(customer_id)
        merged = {
            "customerId": customer_id,
            "riskThresholds": _merged(current["riskThresholds"], payload.get("riskThresholds")),
            "anomalyConfig": _merged(current["anomalyConfig"], payload.get("anomalyConfig")),
            "alertConfig": _merged(current["alertConfig"], payload.get("alertConfig")),
            "routeConfig": _merged(current["routeConfig"], payload.get("routeConfig")),
        }
        _validate_thresholds(merged["riskThresholds"])
        with _connect(self.connection_string) as conn:
            with conn.cursor() as cur:
                self._ensure_customer(cur, customer_id)
                cur.execute(
                    """
                    INSERT INTO "CustomerSettings" (
                        "CustomerId", "RiskThresholds", "AnomalyConfig", "AlertConfig", "RouteConfig", "UpdatedAt"
                    )
                    VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, now() AT TIME ZONE 'utc')
                    ON CONFLICT ("CustomerId") DO UPDATE
                    SET
                        "RiskThresholds" = EXCLUDED."RiskThresholds",
                        "AnomalyConfig" = EXCLUDED."AnomalyConfig",
                        "AlertConfig" = EXCLUDED."AlertConfig",
                        "RouteConfig" = EXCLUDED."RouteConfig",
                        "UpdatedAt" = EXCLUDED."UpdatedAt"
                    """,
                    (
                        customer_id,
                        json.dumps(merged["riskThresholds"]),
                        json.dumps(merged["anomalyConfig"]),
                        json.dumps(merged["alertConfig"]),
                        json.dumps(merged["routeConfig"]),
                    ),
                )
                conn.commit()
        return merged

    @staticmethod
    def _ensure_customer(cur: "psycopg.Cursor[Any]", customer_id: str) -> None:
        cur.execute(
            """
            INSERT INTO "Customers" ("CustomerId", "CustomerName")
            VALUES (%s, %s)
            ON CONFLICT ("CustomerId") DO NOTHING
            """,
            (customer_id, f"Customer {customer_id}"),
        )
        cur.execute(
            """
            INSERT INTO "CustomerSettings" ("CustomerId")
            VALUES (%s)
            ON CONFLICT ("CustomerId") DO NOTHING
            """,
            (customer_id,),
        )


def load_runtime_settings(connection_string: str, customer_id: str) -> dict[str, Any]:
    return CustomerSettingsService(connection_string).get_settings(customer_id)


def load_runtime_settings_from_connection(conn: "psycopg.Connection[Any]", customer_id: str) -> dict[str, Any]:
    defaults = default_settings()
    with conn.cursor() as cur:
        CustomerSettingsService._ensure_customer(cur, customer_id)
        cur.execute(
            """
            SELECT "RiskThresholds", "AnomalyConfig", "AlertConfig", "RouteConfig"
            FROM "CustomerSettings"
            WHERE "CustomerId" = %s
            """,
            (customer_id,),
        )
        row = cur.fetchone()
    if row is None:
        return {"customerId": customer_id, **defaults}
    return {
        "customerId": customer_id,
        "riskThresholds": _merged(defaults["riskThresholds"], row[0]),
        "anomalyConfig": _merged(defaults["anomalyConfig"], row[1]),
        "alertConfig": _merged(defaults["alertConfig"], row[2]),
        "routeConfig": _merged(defaults["routeConfig"], row[3]),
    }


def _merged(defaults: dict[str, Any], incoming: Any) -> dict[str, Any]:
    merged = dict(defaults)
    if isinstance(incoming, dict):
        merged.update(incoming)
    return merged


def _validate_thresholds(thresholds: dict[str, Any]) -> None:
    try:
        critical = float(thresholds["CRITICAL"])
        high = float(thresholds["HIGH"])
        medium = float(thresholds["MEDIUM"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("riskThresholds must include numeric CRITICAL, HIGH, and MEDIUM values") from exc
    if not (critical > high > medium > 0):
        raise ValueError("riskThresholds must satisfy CRITICAL > HIGH > MEDIUM > 0")
