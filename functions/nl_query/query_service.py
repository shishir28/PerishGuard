"""Guarded text-to-SQL service for the dashboard chat."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

try:
    import psycopg
except ModuleNotFoundError:
    psycopg = None

try:
    import requests
except ModuleNotFoundError:
    requests = None


MAX_ROWS = 50
QUERY_TIMEOUT_SECONDS = 10
DEFAULT_OLLAMA_MODEL = "llama3.3:70b"

FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|merge|truncate|exec|execute|grant|revoke|backup|restore)\b",
    re.IGNORECASE,
)
CUSTOMER_FILTER = re.compile(r'"?customerid"?\s*=\s*%s', re.IGNORECASE)

SCHEMA_CONTEXT = """
Tables (PostgreSQL, identifiers are case-sensitive — always double-quote):
- "SensorReadings"("CustomerId", "BatchId", "DeviceId", "ProductType", "ReadingAt", "Temperature", "Humidity", "Ethylene", "CO2", "NH3", "VOC", "ShockG", "LightLux")
- "SpoilagePredictions"("CustomerId", "BatchId", "DeviceId", "ProductType", "ModelVersion", "PredictedAt", "SpoilageProbability", "RiskLevel", "EstimatedHoursLeft", "ConfidenceScore", "AvgTempLast1h", "MaxTempLast1h", "TempVariance24h", "ColdChainBreaks", "AlertSent", "AlertSentAt", "AlertChannel")
- "AlertDispatchLog"("PredictionId", "CustomerId", "BatchId", "Channel", "DeliveryStatus", "Provider", "Target", "AlertText", "ErrorMessage", "AttemptedAt")
- "AnomalyEvents"("CustomerId", "BatchId", "DeviceId", "SensorType", "ReadingValue", "BaselineMean", "BaselineStd", "DeviationScore", "AnomalyType", "Severity", "DetectedAt", "Acknowledged")
- "SpoilageLabels"("CustomerId", "BatchId", "ProductType", "Origin", "Destination", "Carrier", "PackagingType", "SupplierId", "PackagedAt", "ExpiresAt", "ActualSpoilageAt", "WasSpoiled", "SpoilageType", "QualityScore")
- "AnalyticsReports"("CustomerId", "ReportType", "GeneratedAt", "PeriodStart", "PeriodEnd", "ReportData", "Summary")
- "vw_BatchRiskSummary"("CustomerId", "BatchId", "ProductType", "Origin", "Destination", "Carrier", "PackagingType", "SupplierId", "PackagedAt", "ExpiresAt", "LastPredictedAt", "SpoilageProbability", "RiskLevel", "EstimatedHoursLeft", "ConfidenceScore", "ColdChainBreaks", "AlertSent")
- "vw_ModelPredictionTruth"("CustomerId", "BatchId", "ProductType", "LastPredictedAt", "SpoilageProbability", "RiskLevel", "EstimatedHoursLeft", "WasSpoiled", "PredictedSpoiled", "OutcomeLabel", "AbsoluteError")
- "vw_ModelPerformanceSummary"("CustomerId", "ProductType", "EvaluatedBatchCount", "SpoiledBatchCount", "AverageSpoilageProbability", "AverageProbabilityWhenSpoiled", "AverageProbabilityWhenFresh", "MeanAbsoluteError", "TruePositiveCount", "FalsePositiveCount", "TrueNegativeCount", "FalseNegativeCount", "Accuracy")
Rules:
- Return exactly one PostgreSQL SELECT statement.
- Use WHERE "CustomerId" = %s in every query.
- Do not include comments, semicolons, DML, DDL, variables, temp tables, or multiple statements.
- Use LIMIT 50 unless the user asks for fewer rows.
"""


@dataclass(frozen=True)
class QueryResult:
    sql: str
    rows: list[dict[str, Any]]
    summary: str
    chart: str


class NaturalLanguageQueryService:
    def __init__(
        self,
        connection_string: str,
        ollama_endpoint: str | None = None,
        ollama_model: str = DEFAULT_OLLAMA_MODEL,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.connection_string = connection_string
        self.ollama_endpoint = ollama_endpoint.rstrip("/") if ollama_endpoint else None
        self.ollama_model = ollama_model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "NaturalLanguageQueryService":
        return cls(
            connection_string=os.environ["SQL_CONNECTION_STRING"],
            ollama_endpoint=os.getenv("OLLAMA_ENDPOINT"),
            ollama_model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        )

    def answer(self, question: str, customer_id: str) -> dict[str, Any]:
        sql = self.generate_sql(question)
        validate_sql(sql)
        rows = self.execute(sql, customer_id)
        summary = self.summarize(question, rows)
        chart = suggest_chart(question, rows)
        return QueryResult(sql=sql, rows=rows, summary=summary, chart=chart).__dict__

    def generate_sql(self, question: str) -> str:
        fallback = fallback_sql(question)
        if is_prebuilt_question(question):
            return fallback
        if requests is None or self.ollama_endpoint is None:
            return fallback

        prompt = (
            "Convert the question to PostgreSQL SQL for the PerishGuard dashboard.\n"
            f"{SCHEMA_CONTEXT}\n"
            f"Question: {question}\n"
            "SQL:"
        )
        try:
            response = requests.post(
                f"{self.ollama_endpoint}/api/generate",
                json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            sql = response.json().get("response", "").strip()
            return strip_code_fence(sql) or fallback
        except Exception:
            return fallback

    def execute(self, sql: str, customer_id: str) -> list[dict[str, Any]]:
        if psycopg is None:
            raise RuntimeError("psycopg is required for Postgres access. Install functions/requirements.txt.")

        with psycopg.connect(
            self.connection_string,
            autocommit=True,
            options=f"-c statement_timeout={QUERY_TIMEOUT_SECONDS * 1000}",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (customer_id,))
                columns = [column[0] for column in cursor.description]
                rows = []
                for row in cursor.fetchmany(MAX_ROWS):
                    rows.append({columns[i]: row[i] for i in range(len(columns))})
                return rows

    def summarize(self, question: str, rows: list[dict[str, Any]]) -> str:
        fallback = template_summary(question, rows)
        if requests is None or self.ollama_endpoint is None:
            return fallback

        prompt = (
            "Summarize these query results for an operations dashboard in two concise sentences. "
            "Do not mention SQL or implementation details.\n"
            f"Question: {question}\nRows: {json.dumps(rows[:20], default=str)}"
        )
        try:
            response = requests.post(
                f"{self.ollama_endpoint}/api/generate",
                json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json().get("response", "").strip() or fallback
        except Exception:
            return fallback


def validate_sql(sql: str) -> None:
    normalized = " ".join(sql.strip().split())
    if not normalized.lower().startswith("select "):
        raise ValueError("Only SELECT queries are allowed")
    if ";" in normalized or "--" in normalized or "/*" in normalized:
        raise ValueError("Multiple statements and comments are not allowed")
    if FORBIDDEN_SQL.search(normalized):
        raise ValueError("Query contains a forbidden SQL keyword")
    if not CUSTOMER_FILTER.search(normalized):
        raise ValueError("Query must include WHERE CustomerId = ?")


def fallback_sql(question: str) -> str:
    q = question.lower()
    if "performance" in q or "accuracy" in q or "false positive" in q or "false negative" in q:
        return (
            'SELECT "ProductType", "EvaluatedBatchCount", "Accuracy", "MeanAbsoluteError", '
            '"TruePositiveCount", "FalsePositiveCount", "TrueNegativeCount", "FalseNegativeCount" '
            'FROM "vw_ModelPerformanceSummary" '
            'WHERE "CustomerId" = %s ORDER BY "EvaluatedBatchCount" DESC LIMIT 50'
        )
    if "anomal" in q:
        return (
            'SELECT "EventId", "DetectedAt", "BatchId", "DeviceId", "SensorType", "ReadingValue", '
            '"AnomalyType", "Severity", "Acknowledged" FROM "AnomalyEvents" '
            'WHERE "CustomerId" = %s ORDER BY "DetectedAt" DESC LIMIT 50'
        )
    if "spoil" in q or "risk" in q or "critical" in q:
        return (
            'SELECT "LastPredictedAt", "BatchId", "ProductType", "SpoilageProbability", '
            '"RiskLevel", "EstimatedHoursLeft", "ColdChainBreaks" FROM "vw_BatchRiskSummary" '
            'WHERE "CustomerId" = %s AND "LastPredictedAt" IS NOT NULL '
            'ORDER BY "SpoilageProbability" DESC LIMIT 50'
        )
    return (
        'SELECT "ReadingAt", "BatchId", "DeviceId", "ProductType", "Temperature", "Humidity" '
        'FROM "SensorReadings" WHERE "CustomerId" = %s ORDER BY "ReadingAt" DESC LIMIT 50'
    )


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:sql)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


def is_prebuilt_question(question: str) -> bool:
    q = question.strip().lower()
    return q in {
        "show me the highest risk batches",
        "show me the latest anomalies",
        "show me the latest sensor readings",
    }


def template_summary(question: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No matching records were found for this customer."
    q = question.lower()
    if "anomal" in q:
        latest = rows[0]
        severity_counts = _count_values(rows, "Severity")
        top_severity = severity_counts[0][0] if severity_counts else "mixed"
        return (
            f"Found {len(rows)} recent anomalies. "
            f"The latest event is {latest.get('SensorType', 'sensor')} {latest.get('AnomalyType', 'signal')} "
            f"on batch {latest.get('BatchId', 'unknown')} with {top_severity.lower()} severity dominating the current feed."
        )
    if "performance" in q or "accuracy" in q or "false positive" in q or "false negative" in q:
        first = rows[0]
        product = first.get("ProductType", "the top product group")
        accuracy = _format_percent(first.get("Accuracy"))
        mae = _format_hours(first.get("MeanAbsoluteError"))
        return (
            f"Model performance returned {len(rows)} grouped rows. "
            f"{product} is the leading segment with accuracy at {accuracy} and mean absolute error at {mae}."
        )
    if "spoil" in q or "risk" in q or "critical" in q:
        top = rows[0]
        risk_level = str(top.get("RiskLevel") or "UNKNOWN").lower()
        probability = _format_percent(top.get("SpoilageProbability"))
        hours_left = _format_hours(top.get("EstimatedHoursLeft"))
        return (
            f"Found {len(rows)} predicted batches with live risk scores. "
            f"The highest-risk batch is {top.get('BatchId', 'unknown')} ({top.get('ProductType', 'unknown product')}) "
            f"at {risk_level} risk with spoilage probability {probability} and about {hours_left} remaining."
        )
    latest = rows[0]
    temperature = _format_number(latest.get("Temperature"))
    humidity = _format_number(latest.get("Humidity"))
    return (
        f"Found {len(rows)} recent telemetry readings. "
        f"The latest reading is for batch {latest.get('BatchId', 'unknown')} on device {latest.get('DeviceId', 'unknown')} "
        f"at {temperature} C and {humidity}% humidity."
    )


def _count_values(rows: list[dict[str, Any]], key: str) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "UNKNOWN")
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)


def _format_percent(value: Any) -> str:
    try:
        return f"{round(float(value) * 100)}%"
    except (TypeError, ValueError):
        return "—"


def _format_hours(value: Any) -> str:
    try:
        return f"{float(value):.1f}h"
    except (TypeError, ValueError):
        return "—"


def _format_number(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


def suggest_chart(question: str, rows: list[dict[str, Any]]) -> str:
    q = question.lower()
    if not rows:
        return "none"
    if "trend" in q or "over time" in q or any("At" in key for key in rows[0]):
        return "line"
    if "compare" in q or "by " in q:
        return "bar"
    return "table"
