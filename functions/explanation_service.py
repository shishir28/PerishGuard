"""Operator-facing explanation service for Option 1 architecture.

This layer explains model output and suggests actions without changing the
authoritative ONNX-based prediction itself.
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    import requests
except ModuleNotFoundError:
    requests = None


DEFAULT_OLLAMA_MODEL = "llama3.3:70b"


class ExplanationService:
    def __init__(
        self,
        ollama_endpoint: str | None = None,
        ollama_model: str = DEFAULT_OLLAMA_MODEL,
        timeout_seconds: float = 6.0,
    ) -> None:
        self.ollama_endpoint = ollama_endpoint.rstrip("/") if ollama_endpoint else None
        self.ollama_model = ollama_model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "ExplanationService":
        return cls(
            ollama_endpoint=os.getenv("OLLAMA_ENDPOINT"),
            ollama_model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        )

    def explain_batch(
        self,
        summary: dict[str, Any],
        anomalies: list[dict[str, Any]],
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        context = build_explanation_context(summary, anomalies, settings)
        fallback = deterministic_explanation(context)
        if requests is None or self.ollama_endpoint is None:
            return fallback

        prompt = (
            "You are writing operator-facing explanations for a perishable logistics control tower.\n"
            "Use the structured context below. Do not change the risk score or hours-left value. "
            "Explain the likely drivers and recommend the next operational action.\n"
            "Return valid JSON with exactly these keys: "
            'summary, recommendedAction, contributingFactors.\n\n'
            f"Context: {json.dumps(context, default=str)}"
        )
        try:
            response = requests.post(
                f"{self.ollama_endpoint}/api/generate",
                json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            generated = parse_generated_json(response.json().get("response", ""))
            if not generated:
                return fallback
            return {
                "summary": str(generated.get("summary") or fallback["summary"]),
                "recommendedAction": str(
                    generated.get("recommendedAction") or fallback["recommendedAction"]
                ),
                "contributingFactors": normalize_factors(
                    generated.get("contributingFactors"),
                    fallback["contributingFactors"],
                ),
                "generatedBy": "ollama",
            }
        except Exception:
            return fallback


def build_explanation_context(
    summary: dict[str, Any],
    anomalies: list[dict[str, Any]],
    settings: dict[str, Any],
) -> dict[str, Any]:
    alert_config = settings.get("alertConfig", {})
    return {
        "batch": {
            "batchId": summary.get("BatchId"),
            "customerId": summary.get("CustomerId"),
            "productType": summary.get("ProductType"),
            "origin": summary.get("Origin"),
            "destination": summary.get("Destination"),
            "carrier": summary.get("Carrier"),
        },
        "prediction": {
            "riskLevel": summary.get("RiskLevel"),
            "spoilageProbability": float(summary.get("SpoilageProbability") or 0.0),
            "estimatedHoursLeft": float(summary.get("EstimatedHoursLeft") or 0.0),
            "coldChainBreaks": int(summary.get("ColdChainBreaks") or 0),
            "alertSent": bool(summary.get("AlertSent")),
        },
        "settings": {
            "logisticsHoursLeftTrigger": float(alert_config.get("logisticsHoursLeftTrigger", 12)),
            "cooldownMinutes": float(alert_config.get("cooldownMinutes", 30)),
        },
        "anomalies": [
            {
                "sensorType": anomaly.get("SensorType"),
                "anomalyType": anomaly.get("AnomalyType"),
                "severity": anomaly.get("Severity"),
                "readingValue": anomaly.get("ReadingValue"),
                "acknowledged": bool(anomaly.get("Acknowledged")),
            }
            for anomaly in anomalies[:8]
        ],
    }


def deterministic_explanation(context: dict[str, Any]) -> dict[str, Any]:
    batch = context["batch"]
    prediction = context["prediction"]
    anomalies = context["anomalies"]
    risk = str(prediction["riskLevel"] or "LOW")
    probability = float(prediction["spoilageProbability"])
    hours_left = float(prediction["estimatedHoursLeft"])
    cold_chain_breaks = int(prediction["coldChainBreaks"])
    logistics_trigger = float(context["settings"]["logisticsHoursLeftTrigger"])

    factors = [
        f"{risk} spoilage risk at {probability:.0%} probability",
        f"Estimated shelf-life remaining is {hours_left:.1f} hours",
    ]
    if cold_chain_breaks > 0:
        factors.append(
            f"Cold-chain continuity has broken {cold_chain_breaks} time{'s' if cold_chain_breaks != 1 else ''}"
        )

    top_anomalies = [
        f"{item['severity']} {item['sensorType']} {item['anomalyType']}".strip()
        for item in anomalies[:3]
        if item.get("sensorType") and item.get("anomalyType")
    ]
    if top_anomalies:
        factors.append(f"Latest anomaly signals: {', '.join(top_anomalies)}")

    summary = (
        f"Batch {batch['batchId']} is showing {risk.lower()} spoilage risk "
        f"({probability:.0%}) with about {hours_left:.1f} hours remaining on the current model estimate."
    )
    if top_anomalies:
        summary += f" The strongest drivers are {', '.join(top_anomalies)}."
    elif cold_chain_breaks > 0:
        summary += " Recent cold-chain breaks are the strongest structured warning signal."
    else:
        summary += " The current risk is driven primarily by the batch telemetry history captured so far."

    if risk == "CRITICAL" and hours_left < logistics_trigger:
        action = (
            "Escalate immediately to logistics and quality, evaluate reroute or nearest cold storage, "
            "and notify downstream stakeholders of likely spoilage exposure."
        )
    elif risk in {"HIGH", "CRITICAL"}:
        action = (
            "Prioritize manual review, inspect temperature handling on the active route, and prepare a quality hold "
            "if the next readings do not recover."
        )
    elif risk == "MEDIUM":
        action = (
            "Increase monitoring cadence, confirm route handling conditions, and keep operators ready for intervention "
            "if risk or anomaly severity rises."
        )
    else:
        action = "Continue normal monitoring and watch for repeat anomalies before escalating."

    return {
        "summary": summary,
        "recommendedAction": action,
        "contributingFactors": factors[:4],
        "generatedBy": "deterministic",
    }


def parse_generated_json(text: str) -> dict[str, Any] | None:
    cleaned = strip_code_fence(text)
    try:
        parsed = json.loads(cleaned)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def strip_code_fence(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


def normalize_factors(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        normalized = [str(item).strip() for item in value if str(item).strip()]
        if normalized:
            return normalized[:4]
    return fallback[:4]
