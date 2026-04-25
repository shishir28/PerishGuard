"""Create a local SQLite database that mirrors the SQL Server schema
(`sql/*.sql`) and seed it with synthetic data for training.

The production target is SQL Server. SQLite is used here so the training
pipeline can run with zero infra. Columns and semantics match — only the
dialect-specific DDL is different.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from config import DB_PATH
from synthetic_data import generate

SQLITE_SCHEMA = """
DROP TABLE IF EXISTS SensorReadings;
DROP TABLE IF EXISTS SpoilageLabels;
DROP TABLE IF EXISTS SpoilagePredictions;
DROP TABLE IF EXISTS AnomalyEvents;
DROP TABLE IF EXISTS AnalyticsReports;
DROP VIEW  IF EXISTS vw_BatchRiskSummary;

CREATE TABLE SensorReadings (
    ReadingId   INTEGER PRIMARY KEY AUTOINCREMENT,
    BatchId     TEXT    NOT NULL,
    CustomerId  TEXT    NOT NULL,
    DeviceId    TEXT    NOT NULL,
    ProductType TEXT    NOT NULL,
    ReadingAt   TEXT    NOT NULL,
    Temperature REAL,
    Humidity    REAL,
    Ethylene    REAL,
    CO2         REAL,
    NH3         REAL,
    VOC         REAL,
    ShockG      REAL,
    LightLux    REAL,
    IngestedAt  TEXT    DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IX_SensorReadings_Batch ON SensorReadings (BatchId, ReadingAt);

CREATE TABLE SpoilageLabels (
    BatchId          TEXT PRIMARY KEY,
    CustomerId       TEXT NOT NULL,
    ProductType      TEXT NOT NULL,
    Origin           TEXT NOT NULL,
    Destination      TEXT NOT NULL,
    Carrier          TEXT NOT NULL,
    PackagingType    TEXT NOT NULL,
    SupplierId       TEXT NOT NULL,
    PackagedAt       TEXT NOT NULL,
    ExpiresAt        TEXT NOT NULL,
    ActualSpoilageAt TEXT,
    WasSpoiled       INTEGER NOT NULL,
    SpoilageType     TEXT,
    QualityScore     INTEGER,
    CreatedAt        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE SpoilagePredictions (
    PredictionId        INTEGER PRIMARY KEY AUTOINCREMENT,
    BatchId             TEXT NOT NULL,
    CustomerId          TEXT NOT NULL,
    DeviceId            TEXT NOT NULL,
    ProductType         TEXT NOT NULL,
    ModelVersion        TEXT NOT NULL,
    PredictedAt         TEXT DEFAULT CURRENT_TIMESTAMP,
    SpoilageProbability REAL NOT NULL,
    RiskLevel           TEXT NOT NULL,
    EstimatedHoursLeft  REAL,
    ConfidenceScore     REAL,
    AvgTempLast1h       REAL,
    MaxTempLast1h       REAL,
    TempVariance24h     REAL,
    ColdChainBreaks     INTEGER NOT NULL DEFAULT 0,
    AlertSent           INTEGER NOT NULL DEFAULT 0,
    AlertSentAt         TEXT,
    AlertChannel        TEXT
);
CREATE INDEX IX_SpoilagePredictions_Batch ON SpoilagePredictions (BatchId, PredictedAt DESC);

CREATE TABLE AnomalyEvents (
    EventId        INTEGER PRIMARY KEY AUTOINCREMENT,
    BatchId        TEXT NOT NULL,
    CustomerId     TEXT NOT NULL,
    DeviceId       TEXT NOT NULL,
    SensorType     TEXT NOT NULL,
    ReadingValue   REAL NOT NULL,
    BaselineMean   REAL,
    BaselineStd    REAL,
    DeviationScore REAL,
    AnomalyType    TEXT NOT NULL,
    Severity       TEXT NOT NULL,
    DetectedAt     TEXT DEFAULT CURRENT_TIMESTAMP,
    Acknowledged   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE AnalyticsReports (
    ReportId    INTEGER PRIMARY KEY AUTOINCREMENT,
    CustomerId   TEXT,
    ReportType  TEXT NOT NULL,
    GeneratedAt TEXT DEFAULT CURRENT_TIMESTAMP,
    PeriodStart TEXT NOT NULL,
    PeriodEnd   TEXT NOT NULL,
    ReportData  TEXT NOT NULL,
    Summary     TEXT
);

CREATE VIEW vw_BatchRiskSummary AS
SELECT
    l.BatchId, l.CustomerId, l.ProductType, l.Origin, l.Destination, l.Carrier,
    l.PackagingType, l.SupplierId, l.PackagedAt, l.ExpiresAt, l.ActualSpoilageAt,
    l.WasSpoiled, l.SpoilageType, l.QualityScore,
    p.PredictedAt AS LastPredictedAt, p.SpoilageProbability, p.RiskLevel,
    p.EstimatedHoursLeft, p.ConfidenceScore, p.ColdChainBreaks,
    p.AlertSent, p.AlertSentAt, p.AlertChannel
FROM SpoilageLabels l
LEFT JOIN SpoilagePredictions p
    ON p.BatchId = l.BatchId
   AND p.PredictedAt = (SELECT MAX(PredictedAt) FROM SpoilagePredictions WHERE BatchId = l.BatchId);
"""


def seed(n_batches: int = 400, seed: int = 42) -> None:
    print(f"Generating {n_batches} batches of synthetic data...")
    labels, readings = generate(n_batches=n_batches, seed=seed)
    print(f"  {len(readings):,} sensor readings, overall spoilage rate {labels['WasSpoiled'].mean():.1%}")

    # Datetime → ISO strings for SQLite.
    for df, dt_cols in [
        (labels, ["PackagedAt", "ExpiresAt", "ActualSpoilageAt"]),
        (readings, ["ReadingAt"]),
    ]:
        for col in dt_cols:
            df[col] = pd.to_datetime(df[col]).dt.strftime("%Y-%m-%d %H:%M:%S").where(df[col].notna(), None)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    print(f"Writing SQLite database at {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SQLITE_SCHEMA)
        labels.to_sql("SpoilageLabels", conn, if_exists="append", index=False)
        readings.to_sql("SensorReadings", conn, if_exists="append", index=False)
        conn.commit()
    finally:
        conn.close()
    print("Seed complete.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--batches", type=int, default=400)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    seed(n_batches=args.batches, seed=args.seed)
