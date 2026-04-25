"""Business intelligence report generation for PerishGuard."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

try:
    import psycopg
except ModuleNotFoundError:
    psycopg = None


REPORT_TYPES = ("route", "carrier", "packaging", "seasonal", "vendor")


@dataclass(frozen=True)
class AnalyticsReport:
    customer_id: str | None
    report_type: str
    period_start: datetime
    period_end: datetime
    data: list[dict[str, Any]]
    summary: str


class AnalyticsBatchService:
    def __init__(self, connection_string: str) -> None:
        self.connection_string = connection_string

    @classmethod
    def from_environment(cls) -> "AnalyticsBatchService":
        return cls(connection_string=os.environ["SQL_CONNECTION_STRING"])

    def run(self) -> int:
        if psycopg is None:
            raise RuntimeError("psycopg is required for Postgres access. Install functions/requirements.txt.")

        period_end = datetime.now(timezone.utc).replace(microsecond=0)
        period_start = period_end - timedelta(days=7)

        with psycopg.connect(self.connection_string, autocommit=False) as conn:
            batches = load_batch_metrics(conn, period_start, period_end)
            reports = build_reports(batches, period_start, period_end)
            for report in reports:
                insert_report(conn, report)
            conn.commit()
            return len(reports)


def load_batch_metrics(conn: Any, period_start: datetime, period_end: datetime) -> pd.DataFrame:
    query = """
        SELECT
            l."CustomerId", l."BatchId", l."ProductType", l."Origin", l."Destination",
            l."Carrier", l."PackagingType", l."SupplierId", l."PackagedAt", l."ExpiresAt",
            l."WasSpoiled", l."QualityScore",
            r."SpoilageProbability", r."RiskLevel", r."EstimatedHoursLeft", r."ColdChainBreaks"
        FROM "SpoilageLabels" l
        LEFT JOIN "vw_BatchRiskSummary" r ON r."BatchId" = l."BatchId"
        WHERE l."PackagedAt" >= %s AND l."PackagedAt" < %s
    """
    with conn.cursor() as cur:
        cur.execute(query, [period_start, period_end])
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=columns)


def build_reports(batches: pd.DataFrame, period_start: datetime, period_end: datetime) -> list[AnalyticsReport]:
    if batches.empty:
        return [
            AnalyticsReport(None, report_type, period_start, period_end, [], f"No {report_type} activity in this period.")
            for report_type in REPORT_TYPES
        ]

    batches = batches.copy()
    batches["PackagedAt"] = pd.to_datetime(batches["PackagedAt"])
    batches["SpoilageProbability"] = pd.to_numeric(batches["SpoilageProbability"], errors="coerce").fillna(0)
    batches["ColdChainBreaks"] = pd.to_numeric(batches["ColdChainBreaks"], errors="coerce").fillna(0)
    batches["QualityScore"] = pd.to_numeric(batches["QualityScore"], errors="coerce")
    batches["WasSpoiled"] = pd.to_numeric(batches["WasSpoiled"], errors="coerce").fillna(0)

    return [
        _route_report(batches, period_start, period_end),
        _carrier_report(batches, period_start, period_end),
        _packaging_report(batches, period_start, period_end),
        _seasonal_report(batches, period_start, period_end),
        _vendor_report(batches, period_start, period_end),
    ]


def _route_report(df: pd.DataFrame, start: datetime, end: datetime) -> AnalyticsReport:
    data = _group_metrics(df, ["Origin", "Destination"])
    for row in data:
        row["route"] = f"{row.pop('Origin')}->{row.pop('Destination')}"
    return AnalyticsReport(None, "route", start, end, data, _summary("route", data, "spoilageRate"))


def _carrier_report(df: pd.DataFrame, start: datetime, end: datetime) -> AnalyticsReport:
    data = _group_metrics(df, ["Carrier"])
    for row in data:
        row["score"] = round(100 - row["spoilageRate"] * 70 - row["avgColdChainBreaks"] * 5, 2)
    return AnalyticsReport(None, "carrier", start, end, data, _summary("carrier", data, "score", descending=False))


def _packaging_report(df: pd.DataFrame, start: datetime, end: datetime) -> AnalyticsReport:
    data = _group_metrics(df, ["PackagingType"])
    return AnalyticsReport(None, "packaging", start, end, data, _summary("packaging", data, "spoilageRate"))


def _seasonal_report(df: pd.DataFrame, start: datetime, end: datetime) -> AnalyticsReport:
    seasonal = df.copy()
    seasonal["Month"] = seasonal["PackagedAt"].dt.month
    seasonal["DayOfWeek"] = seasonal["PackagedAt"].dt.day_name()
    data = _group_metrics(seasonal, ["Month", "DayOfWeek"])
    return AnalyticsReport(None, "seasonal", start, end, data, _summary("seasonal", data, "spoilageRate"))


def _vendor_report(df: pd.DataFrame, start: datetime, end: datetime) -> AnalyticsReport:
    data = _group_metrics(df, ["SupplierId"])
    for row in data:
        row["score"] = round((row["avgQualityScore"] or 0) - row["spoilageRate"] * 50, 2)
    return AnalyticsReport(None, "vendor", start, end, data, _summary("vendor", data, "score", descending=False))


def _group_metrics(df: pd.DataFrame, group_cols: list[str]) -> list[dict[str, Any]]:
    grouped = (
        df.groupby(group_cols, dropna=False)
        .agg(
            batchCount=("BatchId", "count"),
            spoilageRate=("WasSpoiled", "mean"),
            avgSpoilageProbability=("SpoilageProbability", "mean"),
            avgColdChainBreaks=("ColdChainBreaks", "mean"),
            avgQualityScore=("QualityScore", "mean"),
        )
        .reset_index()
    )
    grouped = grouped.sort_values(["spoilageRate", "avgColdChainBreaks"], ascending=[False, False]).head(20)
    return json.loads(grouped.round(4).to_json(orient="records"))


def _summary(report_type: str, data: list[dict[str, Any]], metric: str, descending: bool = True) -> str:
    if not data:
        return f"No {report_type} patterns were available for this period."
    ranked = sorted(data, key=lambda row: row.get(metric) or 0, reverse=descending)
    item = ranked[0]
    label = item.get("route") or item.get("Carrier") or item.get("PackagingType") or item.get("SupplierId") or item
    return f"Top {report_type} signal: {label} with {metric}={item.get(metric)} across {item.get('batchCount')} batches."


def insert_report(conn: Any, report: AnalyticsReport) -> None:
    conn.execute(
        """
        INSERT INTO "AnalyticsReports" (
            "CustomerId", "ReportType", "PeriodStart", "PeriodEnd", "ReportData", "Summary"
        )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        """,
        (
            report.customer_id,
            report.report_type,
            report.period_start,
            report.period_end,
            json.dumps(report.data, default=str),
            report.summary,
        ),
    )
