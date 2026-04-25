"""Generate realistic synthetic batches + sensor readings for model training.

Each batch simulates a cold-chain shipment from packaging to end-of-life.
Spoiled batches get more temperature excursions and accelerated gas buildup;
good batches stay close to their safe operating envelope. Output roughly
matches what the real Azure IoT Hub stream would produce.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from config import PRODUCT_CONFIG, READING_INTERVAL_MINUTES


@dataclass
class Batch:
    batch_id: str
    customer_id: str
    device_id: str
    product_type: str
    origin: str
    destination: str
    carrier: str
    packaging_type: str
    supplier_id: str
    packaged_at: datetime
    expires_at: datetime
    actual_spoilage_at: datetime | None
    was_spoiled: bool
    spoilage_type: str | None
    quality_score: int


SPOILAGE_TYPES_BY_PRODUCT = {
    "dairy":   ["bacterial", "enzymatic"],
    "meat":    ["bacterial"],
    "seafood": ["bacterial"],
    "produce": ["mold", "enzymatic"],
    "bakery":  ["mold", "oxidation"],
}

ORIGINS = ["Fresno", "Auckland", "Osaka", "Seattle", "Rotterdam", "Valencia"]
DESTINATIONS = ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Canberra"]
CARRIERS = ["ColdLink", "FreshFleet", "PolarLine", "BlueRoute"]
PACKAGING_TYPES = ["standard", "insulated", "vacuum", "modified_atmosphere"]


def _make_batch(rng: random.Random, np_rng: np.random.Generator, idx: int, now: datetime) -> Batch:
    product_type = rng.choice(list(PRODUCT_CONFIG.keys()))
    cfg = PRODUCT_CONFIG[product_type]
    packaged_at = now - timedelta(hours=rng.randint(cfg["shelf_hours"] + 24, cfg["shelf_hours"] * 3))
    expires_at = packaged_at + timedelta(hours=cfg["shelf_hours"])

    # Spoilage rate varies by product — seafood/meat fail more often than bakery.
    base_rate = {"seafood": 0.55, "meat": 0.45, "dairy": 0.35, "produce": 0.35, "bakery": 0.15}
    was_spoiled = rng.random() < base_rate[product_type]

    if was_spoiled:
        # Spoilage happens at 50-95% of expected shelf life.
        frac = rng.uniform(0.50, 0.95)
        actual_spoilage_at = packaged_at + timedelta(hours=cfg["shelf_hours"] * frac)
        spoilage_type = rng.choice(SPOILAGE_TYPES_BY_PRODUCT[product_type])
        quality_score = int(np_rng.integers(15, 55))
    else:
        actual_spoilage_at = None
        spoilage_type = None
        quality_score = int(np_rng.integers(75, 100))

    return Batch(
        batch_id=f"B{idx:06d}",
        customer_id=f"C{(idx % 12):03d}",
        device_id=f"D{(idx % 200):04d}",
        product_type=product_type,
        origin=rng.choice(ORIGINS),
        destination=rng.choice(DESTINATIONS),
        carrier=rng.choice(CARRIERS),
        packaging_type=rng.choice(PACKAGING_TYPES),
        supplier_id=f"S{(idx % 30):03d}",
        packaged_at=packaged_at,
        expires_at=expires_at,
        actual_spoilage_at=actual_spoilage_at,
        was_spoiled=was_spoiled,
        spoilage_type=spoilage_type,
        quality_score=quality_score,
    )


def _simulate_readings(
    batch: Batch,
    rng: random.Random,
    np_rng: np.random.Generator,
) -> list[dict]:
    cfg = PRODUCT_CONFIG[batch.product_type]
    # Observe until spoilage (if any) or full shelf life.
    end_at = batch.actual_spoilage_at or batch.expires_at
    total_minutes = max(int((end_at - batch.packaged_at).total_seconds() // 60), READING_INTERVAL_MINUTES)
    n_readings = total_minutes // READING_INTERVAL_MINUTES

    # Schedule cold-chain excursions. Spoiled batches get more and longer ones.
    n_breaks = np_rng.poisson(4.0 if batch.was_spoiled else 1.2)
    breaks = []
    for _ in range(n_breaks):
        start = rng.randint(0, max(n_readings - 1, 1))
        duration = rng.randint(3, 30) if batch.was_spoiled else rng.randint(2, 8)
        magnitude = rng.uniform(3.0, 9.0) if batch.was_spoiled else rng.uniform(1.0, 3.5)
        breaks.append((start, start + duration, magnitude))

    rows = []
    for i in range(n_readings):
        t = batch.packaged_at + timedelta(minutes=i * READING_INTERVAL_MINUTES)
        progress = i / max(n_readings - 1, 1)  # 0..1 through shelf life

        # Temperature: small noise around base, plus any active excursion spike.
        temp = cfg["base_temp"] + np_rng.normal(0, 0.3)
        for b_start, b_end, mag in breaks:
            if b_start <= i <= b_end:
                # Bell-shaped bump across the excursion window.
                center = (b_start + b_end) / 2
                width = max((b_end - b_start) / 2, 1)
                bump = mag * np.exp(-((i - center) ** 2) / (2 * width ** 2))
                temp += bump

        humidity = float(np.clip(np_rng.normal(70, 5), 30, 98))
        if batch.product_type == "bakery":
            humidity = float(np.clip(np_rng.normal(50, 5), 20, 80))

        # Gas build-up: baseline + linear drift with progress, stronger if spoiled.
        drift = progress * (2.5 if batch.was_spoiled else 0.5)
        ethylene = max(0, np_rng.normal(0.3 if batch.product_type == "produce" else 0.05, 0.05) + drift * 0.5)
        co2 = max(400, np_rng.normal(800, 100) + drift * 800)
        nh3 = max(0, np_rng.normal(0.3, 0.1) + drift * (3.0 if batch.product_type in ("meat", "seafood") else 0.5))
        voc = max(0, np_rng.normal(150, 40) + drift * 200)

        # Rare shock + light events. Slightly more frequent on spoiled/damaged batches.
        shock_prob = 0.008 if batch.was_spoiled else 0.003
        shock_g = float(np_rng.uniform(2.5, 9.0)) if rng.random() < shock_prob else float(np_rng.uniform(0.0, 0.8))
        light_prob = 0.01 if batch.was_spoiled else 0.004
        light_lux = float(np_rng.uniform(200, 5000)) if rng.random() < light_prob else 0.0

        rows.append({
            "BatchId": batch.batch_id,
            "CustomerId": batch.customer_id,
            "DeviceId": batch.device_id,
            "ProductType": batch.product_type,
            "ReadingAt": t,
            "Temperature": round(float(temp), 2),
            "Humidity": round(humidity, 1),
            "Ethylene": round(float(ethylene), 3),
            "CO2": round(float(co2), 1),
            "NH3": round(float(nh3), 3),
            "VOC": round(float(voc), 1),
            "ShockG": round(shock_g, 2),
            "LightLux": round(light_lux, 1),
        })
    return rows


def generate(n_batches: int, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    now = datetime(2026, 4, 23, 12, 0, 0)

    batches: list[Batch] = [_make_batch(rng, np_rng, i, now) for i in range(n_batches)]

    label_rows = [{
        "BatchId": b.batch_id,
        "CustomerId": b.customer_id,
        "ProductType": b.product_type,
        "Origin": b.origin,
        "Destination": b.destination,
        "Carrier": b.carrier,
        "PackagingType": b.packaging_type,
        "SupplierId": b.supplier_id,
        "PackagedAt": b.packaged_at,
        "ExpiresAt": b.expires_at,
        "ActualSpoilageAt": b.actual_spoilage_at,
        "WasSpoiled": int(b.was_spoiled),
        "SpoilageType": b.spoilage_type,
        "QualityScore": b.quality_score,
    } for b in batches]

    reading_rows: list[dict] = []
    for b in batches:
        reading_rows.extend(_simulate_readings(b, rng, np_rng))

    return pd.DataFrame(label_rows), pd.DataFrame(reading_rows)


if __name__ == "__main__":
    labels, readings = generate(n_batches=50)
    print(f"Generated {len(labels)} batches, {len(readings):,} readings")
    print(f"Spoilage rate: {labels['WasSpoiled'].mean():.1%}")
    print(labels.groupby("ProductType")["WasSpoiled"].agg(["count", "mean"]))
