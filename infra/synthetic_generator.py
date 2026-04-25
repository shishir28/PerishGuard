"""Synthetic IoT producer for the PerishGuard local stack.

Picks a sample of seeded batches, generates plausible time-series readings
(temperature drift, occasional cold-chain breaks, light-leakage spikes),
and POSTs them to /api/ingest-reading. Use this to drive the live pipeline:
predictions, anomalies, and alert dispatch will populate Postgres so the
dashboard has real data.

Examples:
    .venv/bin/python infra/synthetic_generator.py --batches 10 --readings-per-batch 30
    .venv/bin/python infra/synthetic_generator.py --rate 5 --duration 60   # 5/sec for 60s
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_DSN = (
    "host=localhost port=5432 dbname=perishguard "
    "user=perishguard password=PerishGuard!2026"
)
DEFAULT_INGEST = "http://localhost:7071/api/ingest-reading"

PRODUCT_BASELINE = {
    "produce":  {"temp": 3.5, "humidity": 88.0, "ethylene": 0.08},
    "seafood":  {"temp": 1.0, "humidity": 92.0, "ethylene": 0.02},
    "dairy":    {"temp": 4.0, "humidity": 80.0, "ethylene": 0.01},
    "bakery":   {"temp": 18.0, "humidity": 55.0, "ethylene": 0.0},
    "meat":     {"temp": 0.5, "humidity": 90.0, "ethylene": 0.02},
}


@dataclass
class Batch:
    batch_id: str
    customer_id: str
    product_type: str
    device_id: str


def fetch_batches(dsn: str, limit: int) -> list[Batch]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            'SELECT "BatchId", "CustomerId", "ProductType" FROM "SpoilageLabels" '
            'ORDER BY random() LIMIT %s',
            (limit,),
        )
        rows = cur.fetchall()
    return [
        Batch(batch_id=r[0], customer_id=r[1], product_type=r[2], device_id=f"D-{r[0][-4:]}")
        for r in rows
    ]


def generate_reading(batch: Batch, t: datetime, anomaly_chance: float) -> dict:
    baseline = PRODUCT_BASELINE.get(batch.product_type, PRODUCT_BASELINE["produce"])
    temp = baseline["temp"] + random.gauss(0, 0.4)
    humidity = baseline["humidity"] + random.gauss(0, 1.5)
    ethylene = max(0.0, baseline["ethylene"] + random.gauss(0, 0.005))

    co2 = max(0.0, 400 + random.gauss(0, 30))
    nh3 = max(0.0, random.gauss(0.05, 0.02))
    voc = max(0.0, random.gauss(0.1, 0.04))
    shock = max(0.0, abs(random.gauss(0, 0.3)))
    light = max(0.0, random.gauss(0, 5))

    if random.random() < anomaly_chance:
        kind = random.choice(["temp_break", "shock", "light_leak", "ethylene_spike"])
        if kind == "temp_break":
            temp += random.uniform(6.0, 12.0)
        elif kind == "shock":
            shock += random.uniform(2.5, 6.0)
        elif kind == "light_leak":
            light += random.uniform(300, 800)
        elif kind == "ethylene_spike":
            ethylene += random.uniform(0.4, 1.2)

    return {
        "BatchId":     batch.batch_id,
        "CustomerId":  batch.customer_id,
        "DeviceId":    batch.device_id,
        "ProductType": batch.product_type,
        "ReadingAt":   t.replace(microsecond=0).isoformat(),
        "Temperature": round(temp, 2),
        "Humidity":    round(humidity, 2),
        "Ethylene":    round(ethylene, 4),
        "CO2":         round(co2, 1),
        "NH3":         round(nh3, 4),
        "VOC":         round(voc, 4),
        "ShockG":      round(shock, 3),
        "LightLux":    round(light, 1),
    }


def post_reading(url: str, reading: dict, timeout: float = 30.0) -> tuple[int, str]:
    try:
        resp = requests.post(url, json=reading, timeout=timeout)
        return resp.status_code, resp.text[:200]
    except requests.RequestException as exc:
        return 0, str(exc)[:200]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-dsn", default=os.getenv("PG_DSN", DEFAULT_PG_DSN))
    parser.add_argument("--ingest-url", default=os.getenv("INGEST_URL", DEFAULT_INGEST))
    parser.add_argument("--batches", type=int, default=5,
                        help="how many distinct batches to simulate")
    parser.add_argument("--readings-per-batch", type=int, default=20,
                        help="readings per batch in burst mode (default 20)")
    parser.add_argument("--anomaly-chance", type=float, default=0.15,
                        help="probability per reading of injecting an anomaly")
    parser.add_argument("--rate", type=float, default=0.0,
                        help="continuous mode: readings/sec (overrides burst)")
    parser.add_argument("--duration", type=float, default=30.0,
                        help="seconds to run in continuous mode")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    print(f"fetching {args.batches} random batches from postgres...")
    batches = fetch_batches(args.pg_dsn, args.batches)
    if not batches:
        print("no batches found in SpoilageLabels — run seed_postgres_from_sqlite.py first",
              file=sys.stderr)
        return 1
    print(f"  -> simulating: {[b.batch_id for b in batches]}")
    print(f"  -> ingest: {args.ingest_url}")

    sent = ok = errors = 0

    if args.rate > 0:
        deadline = time.time() + args.duration
        interval = 1.0 / args.rate
        t_clock = datetime.now(timezone.utc)
        while time.time() < deadline:
            batch = random.choice(batches)
            t_clock += timedelta(seconds=interval * 60)  # compress: 1 wall-sec = 1 sim-min
            reading = generate_reading(batch, t_clock, args.anomaly_chance)
            code, body = post_reading(args.ingest_url, reading)
            sent += 1
            if 200 <= code < 300:
                ok += 1
            else:
                errors += 1
                print(f"  ! {code} {body}")
            time.sleep(interval)
    else:
        for batch in batches:
            t_clock = datetime.now(timezone.utc) - timedelta(minutes=args.readings_per_batch)
            for _ in range(args.readings_per_batch):
                t_clock += timedelta(minutes=1)
                reading = generate_reading(batch, t_clock, args.anomaly_chance)
                code, body = post_reading(args.ingest_url, reading)
                sent += 1
                if 200 <= code < 300:
                    ok += 1
                else:
                    errors += 1
                    print(f"  ! {batch.batch_id} {code} {body}")

    print(f"sent={sent} ok={ok} errors={errors}")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
