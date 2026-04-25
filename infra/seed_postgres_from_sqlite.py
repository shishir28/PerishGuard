"""Bootstrap Postgres with the synthetic data already in perishguard.db (SQLite).

Copies SpoilageLabels (~400) and SensorReadings (~345K) into the live Postgres
database used by the Functions runtime. Idempotent: truncates the target tables
before loading. Predictions, anomalies, and reports are intentionally skipped
because those are produced by the live pipeline, not seed data.

Usage:
    .venv/bin/python infra/seed_postgres_from_sqlite.py
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE = REPO_ROOT / "perishguard.db"
DEFAULT_PG_DSN = (
    "host=localhost port=5432 dbname=perishguard "
    "user=perishguard password=PerishGuard!2026"
)

LABEL_COLUMNS = [
    "BatchId", "CustomerId", "ProductType", "Origin", "Destination",
    "Carrier", "PackagingType", "SupplierId", "PackagedAt", "ExpiresAt",
    "ActualSpoilageAt", "WasSpoiled", "SpoilageType", "QualityScore",
]
READING_COLUMNS = [
    "BatchId", "CustomerId", "DeviceId", "ProductType", "ReadingAt",
    "Temperature", "Humidity", "Ethylene", "CO2", "NH3", "VOC",
    "ShockG", "LightLux",
]


def _quoted(columns: list[str]) -> str:
    return ", ".join(f'"{c}"' for c in columns)


def copy_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn: "psycopg.Connection",
    table: str,
    columns: list[str],
    batch_size: int = 5000,
) -> int:
    select_sql = f'SELECT {", ".join(columns)} FROM "{table}"'
    cursor = sqlite_conn.execute(select_sql)
    quoted_cols = _quoted(columns)
    copy_sql = f'COPY "{table}" ({quoted_cols}) FROM STDIN'

    rows_copied = 0
    with pg_conn.cursor() as pg_cur, pg_cur.copy(copy_sql) as copy:
        while True:
            batch = cursor.fetchmany(batch_size)
            if not batch:
                break
            for row in batch:
                copy.write_row(row)
            rows_copied += len(batch)
    return rows_copied


def sync_customers(pg_conn: "psycopg.Connection") -> None:
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO "Customers" ("CustomerId", "CustomerName")
            SELECT DISTINCT "CustomerId", 'Customer ' || "CustomerId"
            FROM "SpoilageLabels"
            ON CONFLICT ("CustomerId") DO NOTHING
            """
        )
        cur.execute(
            """
            INSERT INTO "CustomerSettings" ("CustomerId")
            SELECT c."CustomerId"
            FROM "Customers" c
            ON CONFLICT ("CustomerId") DO NOTHING
            """
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE))
    parser.add_argument("--pg-dsn", default=os.getenv("PG_DSN", DEFAULT_PG_DSN))
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        print(f"sqlite source not found: {sqlite_path}", file=sys.stderr)
        return 1

    print(f"source : {sqlite_path}")
    print(f"target : {args.pg_dsn.split(' password=')[0]} password=***")

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = None

    with psycopg.connect(args.pg_dsn, autocommit=False) as pg_conn:
        with pg_conn.cursor() as cur:
            cur.execute('TRUNCATE "SensorReadings", "SpoilageLabels" RESTART IDENTITY CASCADE')

        labels = copy_table(sqlite_conn, pg_conn, "SpoilageLabels", LABEL_COLUMNS)
        print(f"  SpoilageLabels  copied: {labels:>7}")

        readings = copy_table(sqlite_conn, pg_conn, "SensorReadings", READING_COLUMNS)
        print(f"  SensorReadings  copied: {readings:>7}")
        sync_customers(pg_conn)
        print("  Customers synced from labels")

        pg_conn.commit()

    sqlite_conn.close()
    print("seed complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
