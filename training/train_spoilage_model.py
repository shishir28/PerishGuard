"""Train the PerishGuard spoilage classifier + shelf-life regressor.

- 5-fold stratified CV for the classifier (target: WasSpoiled).
- 5-fold CV for the regressor (target: ActualShelfLifeH).
- Exports both models to ONNX (Azure Function consumes them via onnxruntime).
- Emits model_metadata.json with feature list, product mappings, risk
  thresholds, and CV metrics.

Acceptance (from IMPLEMENTATION_PLAN.md Task 1):
  - classifier CV ROC-AUC > 0.80
  - regressor CV MAE  < 12 hours
  - ONNX inference    < 50ms
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from onnxmltools.convert import convert_lightgbm
from onnxmltools.convert.common.data_types import FloatTensorType
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.model_selection import KFold, StratifiedKFold

from config import (
    DB_PATH,
    FEATURE_COLUMNS,
    MODEL_DIR,
    MODEL_VERSION,
    PRODUCT_CONFIG,
    RISK_THRESHOLDS,
)
from features import build_feature_matrix

TARGET_OPSET = 15
N_SPLITS = 5
RANDOM_STATE = 42


def load_data() -> pd.DataFrame:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"{DB_PATH} not found — run `python training/seed_local_db.py` first."
        )
    conn = sqlite3.connect(DB_PATH)
    try:
        labels = pd.read_sql_query("SELECT * FROM SpoilageLabels", conn)
        readings = pd.read_sql_query("SELECT * FROM SensorReadings", conn)
    finally:
        conn.close()
    print(f"Loaded {len(labels)} batches, {len(readings):,} readings")
    return build_feature_matrix(labels, readings)


def build_training_frame(labels: pd.DataFrame, readings: pd.DataFrame) -> pd.DataFrame:
    df = build_feature_matrix(labels, readings)
    if df.empty:
        raise ValueError("No labelled batches with sensor history were available for training")
    return df


def train_classifier(X: np.ndarray, y: np.ndarray) -> tuple[LGBMClassifier, float]:
    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    aucs = []
    for fold, (tr, va) in enumerate(skf.split(X, y), 1):
        m = LGBMClassifier(
            n_estimators=300, learning_rate=0.05, num_leaves=31,
            class_weight="balanced", random_state=RANDOM_STATE, verbose=-1,
        )
        m.fit(X[tr], y[tr])
        proba = m.predict_proba(X[va])[:, 1]
        auc = roc_auc_score(y[va], proba)
        aucs.append(auc)
        print(f"  classifier fold {fold}: ROC-AUC={auc:.4f}")
    cv_auc = float(np.mean(aucs))
    print(f"  classifier CV ROC-AUC: {cv_auc:.4f} (±{np.std(aucs):.4f})")

    final = LGBMClassifier(
        n_estimators=300, learning_rate=0.05, num_leaves=31,
        class_weight="balanced", random_state=RANDOM_STATE, verbose=-1,
    )
    final.fit(X, y)
    return final, cv_auc


def train_regressor(X: np.ndarray, y: np.ndarray) -> tuple[LGBMRegressor, float]:
    kf = KFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    maes = []
    for fold, (tr, va) in enumerate(kf.split(X), 1):
        m = LGBMRegressor(
            n_estimators=400, learning_rate=0.05, num_leaves=31,
            random_state=RANDOM_STATE, verbose=-1,
        )
        m.fit(X[tr], y[tr])
        pred = m.predict(X[va])
        mae = mean_absolute_error(y[va], pred)
        maes.append(mae)
        print(f"  regressor fold {fold}: MAE={mae:.2f}h")
    cv_mae = float(np.mean(maes))
    print(f"  regressor CV MAE: {cv_mae:.2f}h (±{np.std(maes):.2f})")

    final = LGBMRegressor(
        n_estimators=400, learning_rate=0.05, num_leaves=31,
        random_state=RANDOM_STATE, verbose=-1,
    )
    final.fit(X, y)
    return final, cv_mae


def export_onnx(model, n_features: int, out_path: Path, zipmap: bool = False) -> None:
    initial_types = [("input", FloatTensorType([None, n_features]))]
    onnx_model = convert_lightgbm(
        model, initial_types=initial_types, target_opset=TARGET_OPSET, zipmap=zipmap,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(onnx_model.SerializeToString())


def benchmark_inference(onnx_path: Path, n_features: int, runs: int = 200) -> float:
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    input_name = sess.get_inputs()[0].name
    x = np.random.rand(1, n_features).astype(np.float32)
    # Warm-up.
    for _ in range(10):
        sess.run(None, {input_name: x})
    t0 = time.perf_counter()
    for _ in range(runs):
        sess.run(None, {input_name: x})
    elapsed = (time.perf_counter() - t0) / runs * 1000
    return elapsed


def train_and_export(
    df: pd.DataFrame,
    model_dir: Path = MODEL_DIR,
    model_version: str = MODEL_VERSION,
    metadata_extra: dict[str, object] | None = None,
) -> dict[str, object]:
    print(f"Feature matrix: {df.shape[0]} rows × {len(FEATURE_COLUMNS)} features")
    print(f"Spoilage rate: {df['WasSpoiled'].mean():.1%}")

    X = df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y_cls = df["WasSpoiled"].to_numpy(dtype=np.int64)
    y_reg = df["ActualShelfLifeH"].to_numpy(dtype=np.float32)

    print("\n== Training classifier ==")
    cls, cv_auc = train_classifier(X, y_cls)

    print("\n== Training regressor ==")
    reg, cv_mae = train_regressor(X, y_reg)

    print("\n== Exporting ONNX ==")
    model_dir.mkdir(parents=True, exist_ok=True)
    cls_path = model_dir / "spoilage_classifier.onnx"
    reg_path = model_dir / "shelf_life_regressor.onnx"
    export_onnx(cls, X.shape[1], cls_path)
    export_onnx(reg, X.shape[1], reg_path)
    print(f"  wrote {cls_path}")
    print(f"  wrote {reg_path}")

    print("\n== Inference benchmark ==")
    cls_ms = benchmark_inference(cls_path, X.shape[1])
    reg_ms = benchmark_inference(reg_path, X.shape[1])
    print(f"  classifier: {cls_ms:.2f} ms / call")
    print(f"  regressor:  {reg_ms:.2f} ms / call")

    metadata: dict[str, object] = {
        "model_version": model_version,
        "trained_at": pd.Timestamp.now("UTC").isoformat(),
        "feature_columns": FEATURE_COLUMNS,
        "product_config": {k: v for k, v in PRODUCT_CONFIG.items()},
        "risk_thresholds": RISK_THRESHOLDS,
        "cv_metrics": {
            "classifier_roc_auc": round(cv_auc, 4),
            "regressor_mae_hours": round(cv_mae, 2),
            "n_splits": N_SPLITS,
        },
        "inference_ms": {
            "classifier": round(cls_ms, 2),
            "regressor": round(reg_ms, 2),
        },
        "artefacts": {
            "classifier_onnx": cls_path.name,
            "regressor_onnx": reg_path.name,
        },
    }
    if metadata_extra:
        metadata.update(metadata_extra)

    meta_path = model_dir / "model_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2))
    print(f"  wrote {meta_path}")

    print("\n== Acceptance checks ==")
    checks = [
        ("classifier CV ROC-AUC > 0.80", cv_auc > 0.80, f"{cv_auc:.4f}"),
        ("regressor CV MAE < 12h", cv_mae < 12.0, f"{cv_mae:.2f}h"),
        ("classifier inference < 50ms", cls_ms < 50, f"{cls_ms:.2f}ms"),
        ("regressor inference < 50ms", reg_ms < 50, f"{reg_ms:.2f}ms"),
    ]
    for name, passed, value in checks:
        flag = "PASS" if passed else "FAIL"
        print(f"  [{flag}] {name}: {value}")

    return {
        "model_version": model_version,
        "batch_count": int(df.shape[0]),
        "cv_metrics": metadata["cv_metrics"],
        "inference_ms": metadata["inference_ms"],
        "artefacts": metadata["artefacts"],
        "metadata_path": str(meta_path),
        "checks": [{"name": name, "passed": passed, "value": value} for name, passed, value in checks],
    }


def main() -> None:
    df = load_data()
    train_and_export(df)


if __name__ == "__main__":
    main()
