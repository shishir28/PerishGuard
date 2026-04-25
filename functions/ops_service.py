"""Operational read/write services for dashboard actions."""

from __future__ import annotations

import os
from typing import Any

try:
    import psycopg
except ModuleNotFoundError:
    psycopg = None

try:
    from functions.customer_settings import CustomerSettingsService
    from functions.explanation_service import ExplanationService
except ModuleNotFoundError:
    from customer_settings import CustomerSettingsService
    from explanation_service import ExplanationService


def _connection_string() -> str:
    return os.environ["SQL_CONNECTION_STRING"]


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError("psycopg is required for Postgres access. Install functions/requirements.txt.")


def _fetch_all(cursor: "psycopg.Cursor[Any]") -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    return [{columns[i]: row[i] for i in range(len(columns))} for row in cursor.fetchall()]


class OperationsService:
    @classmethod
    def from_environment(cls) -> "OperationsService":
        return cls(_connection_string())

    def __init__(self, connection_string: str) -> None:
        self.connection_string = connection_string
        self.settings_service = CustomerSettingsService(connection_string)
        self.explanation_service = ExplanationService.from_environment()

    def acknowledge_anomaly(self, customer_id: str, event_id: int) -> dict[str, Any]:
        _require_psycopg()
        with psycopg.connect(self.connection_string, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE "AnomalyEvents"
                    SET "Acknowledged" = 1
                    WHERE "EventId" = %s AND "CustomerId" = %s AND "Acknowledged" = 0
                    RETURNING "EventId", "BatchId", "CustomerId", "DetectedAt", "Acknowledged"
                    """,
                    (event_id, customer_id),
                )
                row = cur.fetchone()
                if row is None:
                    cur.execute(
                        """
                        SELECT "EventId", "Acknowledged"
                        FROM "AnomalyEvents"
                        WHERE "EventId" = %s AND "CustomerId" = %s
                        """,
                        (event_id, customer_id),
                    )
                    existing = cur.fetchone()
                    if existing is None:
                        raise LookupError("Anomaly event not found for this customer")
                    if int(existing[1]) == 1:
                        raise ValueError("Anomaly event is already acknowledged")
                    raise LookupError("Unable to acknowledge anomaly event")
            conn.commit()
        return {
            "eventId": row[0],
            "batchId": row[1],
            "customerId": row[2],
            "detectedAt": row[3],
            "acknowledged": bool(row[4]),
        }

    def batch_detail(self, customer_id: str, batch_id: str) -> dict[str, Any]:
        _require_psycopg()
        with psycopg.connect(self.connection_string, autocommit=True) as conn:
            summary = self._fetch_one(
                conn,
                """
                SELECT *
                FROM "vw_BatchRiskSummary"
                WHERE "CustomerId" = %s AND "BatchId" = %s
                """,
                (customer_id, batch_id),
            )
            if summary is None:
                raise LookupError("Batch not found for this customer")

            sensor_history = self._fetch_all(
                conn,
                """
                SELECT *
                FROM (
                    SELECT "ReadingAt", "Temperature", "Humidity", "Ethylene", "CO2", "NH3", "VOC", "ShockG", "LightLux"
                    FROM "SensorReadings"
                    WHERE "CustomerId" = %s AND "BatchId" = %s
                    ORDER BY "ReadingAt" DESC
                    LIMIT 120
                ) r
                ORDER BY "ReadingAt"
                """,
                (customer_id, batch_id),
            )
            prediction_history = self._fetch_all(
                conn,
                """
                SELECT "PredictionId", "PredictedAt", "SpoilageProbability", "RiskLevel",
                       "EstimatedHoursLeft", "ConfidenceScore", "ColdChainBreaks",
                       "AlertSent", "AlertSentAt", "AlertChannel"
                FROM "SpoilagePredictions"
                WHERE "CustomerId" = %s AND "BatchId" = %s
                ORDER BY "PredictedAt" ASC
                LIMIT 120
                """,
                (customer_id, batch_id),
            )
            anomalies = self._fetch_all(
                conn,
                """
                SELECT "EventId", "DetectedAt", "SensorType", "ReadingValue", "BaselineMean",
                       "BaselineStd", "DeviationScore", "AnomalyType", "Severity", "Acknowledged"
                FROM "AnomalyEvents"
                WHERE "CustomerId" = %s AND "BatchId" = %s
                ORDER BY "DetectedAt" DESC
                LIMIT 50
                """,
                (customer_id, batch_id),
            )
            alert_log = self._fetch_all(
                conn,
                """
                SELECT "LogId", "AttemptedAt", "Channel", "DeliveryStatus", "Provider",
                       "Target", "TaskCount", "ErrorMessage", "AlertText"
                FROM "AlertDispatchLog"
                WHERE "CustomerId" = %s AND "BatchId" = %s
                ORDER BY "AttemptedAt" DESC
                LIMIT 50
                """,
                (customer_id, batch_id),
            )
            settings = self.settings_service.get_settings(customer_id)
            explanation = self.explanation_service.explain_batch(summary, anomalies, settings)

        return {
            "summary": summary,
            "explanation": explanation,
            "sensorHistory": sensor_history,
            "predictionHistory": prediction_history,
            "anomalies": anomalies,
            "alertLog": alert_log,
        }

    def model_performance(self, customer_id: str) -> dict[str, Any]:
        _require_psycopg()
        with psycopg.connect(self.connection_string, autocommit=True) as conn:
            overview = self._fetch_one(
                conn,
                """
                SELECT
                    COUNT(*) AS "EvaluatedBatchCount",
                    AVG("SpoilageProbability") AS "AverageSpoilageProbability",
                    AVG("AbsoluteError") AS "MeanAbsoluteError",
                    AVG(CASE WHEN "PredictedSpoiled" = "WasSpoiled" THEN 1.0 ELSE 0.0 END) AS "Accuracy",
                    SUM(CASE WHEN "OutcomeLabel" = 'TRUE_POSITIVE' THEN 1 ELSE 0 END) AS "TruePositiveCount",
                    SUM(CASE WHEN "OutcomeLabel" = 'FALSE_POSITIVE' THEN 1 ELSE 0 END) AS "FalsePositiveCount",
                    SUM(CASE WHEN "OutcomeLabel" = 'TRUE_NEGATIVE' THEN 1 ELSE 0 END) AS "TrueNegativeCount",
                    SUM(CASE WHEN "OutcomeLabel" = 'FALSE_NEGATIVE' THEN 1 ELSE 0 END) AS "FalseNegativeCount"
                FROM "vw_ModelPredictionTruth"
                WHERE "CustomerId" = %s AND "LastPredictedAt" IS NOT NULL
                """,
                (customer_id,),
            ) or {}
            product_breakdown = self._fetch_all(
                conn,
                """
                SELECT *
                FROM "vw_ModelPerformanceSummary"
                WHERE "CustomerId" = %s
                ORDER BY "EvaluatedBatchCount" DESC, "ProductType"
                """,
                (customer_id,),
            )
            recent_batches = self._fetch_all(
                conn,
                """
                SELECT "BatchId", "ProductType", "LastPredictedAt", "SpoilageProbability",
                       "RiskLevel", "EstimatedHoursLeft", "WasSpoiled", "PredictedSpoiled",
                       "OutcomeLabel", "AbsoluteError"
                FROM "vw_ModelPredictionTruth"
                WHERE "CustomerId" = %s AND "LastPredictedAt" IS NOT NULL
                ORDER BY "LastPredictedAt" DESC
                LIMIT 50
                """,
                (customer_id,),
            )
        return {
            "overview": overview,
            "productBreakdown": product_breakdown,
            "recentBatches": recent_batches,
        }

    def alert_activity(self, customer_id: str) -> dict[str, Any]:
        _require_psycopg()
        with psycopg.connect(self.connection_string, autocommit=True) as conn:
            overview = self._fetch_one(
                conn,
                """
                SELECT
                    COUNT(*) AS "TotalAttempts",
                    COALESCE(SUM(CASE WHEN "DeliveryStatus" = 'sent' THEN 1 ELSE 0 END), 0) AS "SentCount",
                    COALESCE(SUM(CASE WHEN "DeliveryStatus" = 'failed' THEN 1 ELSE 0 END), 0) AS "FailedCount",
                    COALESCE(SUM(CASE WHEN "DeliveryStatus" = 'skipped' THEN 1 ELSE 0 END), 0) AS "SkippedCount",
                    COALESCE(SUM(CASE WHEN "DeliveryStatus" = 'suppressed' THEN 1 ELSE 0 END), 0) AS "SuppressedCount",
                    MAX("AttemptedAt") AS "LastAttemptedAt"
                FROM "AlertDispatchLog"
                WHERE "CustomerId" = %s
                  AND "AttemptedAt" >= (now() AT TIME ZONE 'utc') - INTERVAL '7 days'
                """,
                (customer_id,),
            ) or {}
            channel_breakdown = self._fetch_all(
                conn,
                """
                SELECT
                    "Channel",
                    COUNT(*) AS "AttemptCount",
                    SUM(CASE WHEN "DeliveryStatus" = 'sent' THEN 1 ELSE 0 END) AS "SentCount",
                    SUM(CASE WHEN "DeliveryStatus" = 'failed' THEN 1 ELSE 0 END) AS "FailedCount",
                    SUM(CASE WHEN "DeliveryStatus" = 'skipped' THEN 1 ELSE 0 END) AS "SkippedCount",
                    SUM(CASE WHEN "DeliveryStatus" = 'suppressed' THEN 1 ELSE 0 END) AS "SuppressedCount",
                    MAX("AttemptedAt") AS "LastAttemptedAt"
                FROM "AlertDispatchLog"
                WHERE "CustomerId" = %s
                  AND "AttemptedAt" >= (now() AT TIME ZONE 'utc') - INTERVAL '7 days'
                GROUP BY "Channel"
                ORDER BY "AttemptCount" DESC, "Channel"
                """,
                (customer_id,),
            )
            recent_attempts = self._fetch_all(
                conn,
                """
                SELECT
                    "LogId", "AttemptedAt", "BatchId", "Channel", "DeliveryStatus",
                    "Provider", "Target", "TaskCount", "ErrorMessage", "AlertText"
                FROM "AlertDispatchLog"
                WHERE "CustomerId" = %s
                ORDER BY "AttemptedAt" DESC
                LIMIT 20
                """,
                (customer_id,),
            )
        return {
            "window": "7d",
            "overview": overview,
            "channels": channel_breakdown,
            "recentAttempts": recent_attempts,
        }

    def customer_settings(self, customer_id: str) -> dict[str, Any]:
        return self.settings_service.get_settings(customer_id)

    def update_customer_settings(self, customer_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.settings_service.update_settings(customer_id, payload)

    def route_overview(self, customer_id: str) -> dict[str, Any]:
        _require_psycopg()
        with psycopg.connect(self.connection_string, autocommit=True) as conn:
            routes = self._fetch_all(
                conn,
                """
                SELECT *
                FROM "vw_RouteRiskSummary"
                WHERE "CustomerId" = %s
                ORDER BY "AverageSpoilageProbability" DESC, "CriticalBatchCount" DESC, "BatchCount" DESC
                LIMIT 50
                """,
                (customer_id,),
            )
        return {"routes": routes}

    def model_training_runs(self, customer_id: str) -> dict[str, Any]:
        _require_psycopg()
        with psycopg.connect(self.connection_string, autocommit=True) as conn:
            runs = self._fetch_all(
                conn,
                """
                SELECT
                    "RunId", "RequestedByUserId", "CustomerId", "Status", "StartedAt",
                    "CompletedAt", "ModelVersion", "TrainingMetrics", "OutputDir", "ErrorMessage"
                FROM "ModelTrainingRuns"
                WHERE "CustomerId" IS NULL OR "CustomerId" = %s
                ORDER BY "StartedAt" DESC
                LIMIT 20
                """,
                (customer_id,),
            )
        return {"runs": runs}

    def _fetch_one(
        self,
        conn: "psycopg.Connection[Any]",
        query: str,
        params: tuple[Any, ...],
    ) -> dict[str, Any] | None:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            if row is None:
                return None
            columns = [column[0] for column in cur.description]
            return {columns[i]: row[i] for i in range(len(columns))}

    def _fetch_all(
        self,
        conn: "psycopg.Connection[Any]",
        query: str,
        params: tuple[Any, ...],
    ) -> list[dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return _fetch_all(cur)
