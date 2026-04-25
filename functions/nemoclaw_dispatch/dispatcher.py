"""NemoClaw multi-agent alert dispatch for high-risk batches."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    import requests
except ModuleNotFoundError:
    requests = None


DEFAULT_COOLDOWN_MINUTES = 30
DEFAULT_OLLAMA_MODEL = "llama3.3:70b"


@dataclass(frozen=True)
class AgentTask:
    agent: str
    action: str
    instructions: str


@dataclass(frozen=True)
class DispatchResult:
    should_alert: bool
    alert_sent: bool
    channel: str | None
    alert_text: str | None
    tasks: list[dict[str, Any]]
    error: str | None = None


class AlertDispatcher:
    def __init__(
        self,
        ollama_endpoint: str | None = None,
        nemoclaw_endpoint: str | None = None,
        cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
        ollama_model: str = DEFAULT_OLLAMA_MODEL,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.ollama_endpoint = _clean_endpoint(ollama_endpoint)
        self.nemoclaw_endpoint = _clean_endpoint(nemoclaw_endpoint)
        self.cooldown_minutes = cooldown_minutes
        self.ollama_model = ollama_model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "AlertDispatcher":
        return cls(
            ollama_endpoint=os.getenv("OLLAMA_ENDPOINT"),
            nemoclaw_endpoint=os.getenv("NEMOCLAW_ENDPOINT"),
            cooldown_minutes=int(os.getenv("ALERT_COOLDOWN_MINUTES", str(DEFAULT_COOLDOWN_MINUTES))),
            ollama_model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        )

    def dispatch(self, context: dict[str, Any]) -> DispatchResult:
        tasks = agent_tasks_for_prediction(context)
        if not tasks:
            return DispatchResult(False, False, None, None, [])

        alert_text = self._alert_text(context, tasks)
        if requests is None or self.nemoclaw_endpoint is None:
            return DispatchResult(True, True, "template", alert_text, [_offline_task(task) for task in tasks])

        sent_tasks: list[dict[str, Any]] = []
        try:
            for task in tasks:
                response = requests.post(
                    f"{self.nemoclaw_endpoint}/api/v1/tasks",
                    json={
                        "agent": task.agent,
                        "action": task.action,
                        "instructions": task.instructions,
                        "alertText": alert_text,
                        "context": context,
                    },
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                sent_tasks.append({"agent": task.agent, "status": "sent", "response": _safe_json(response)})
        except Exception as exc:
            return DispatchResult(True, True, "template", alert_text, sent_tasks, error=str(exc))

        return DispatchResult(True, True, "nemoclaw", alert_text, sent_tasks)

    def _alert_text(self, context: dict[str, Any], tasks: list[AgentTask]) -> str:
        fallback = template_alert(context, tasks)
        if requests is None or self.ollama_endpoint is None:
            return fallback

        prompt = (
            "Write a concise operational alert under 200 words for a perishable "
            "food shipment. Include batch, risk, hours left, key anomalies, and "
            "recommended next action. Avoid exposing internal system details.\n\n"
            f"Context: {context}"
        )
        try:
            response = requests.post(
                f"{self.ollama_endpoint}/api/generate",
                json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            text = _safe_json(response).get("response", "").strip()
            return text or fallback
        except Exception:
            return fallback


def agent_tasks_for_prediction(context: dict[str, Any]) -> list[AgentTask]:
    prediction = context["prediction"]
    risk = prediction["riskLevel"]
    hours_left = float(prediction.get("estimatedHoursLeft") or 0.0)

    tasks: list[AgentTask] = []
    if risk == "CRITICAL" and hours_left < 12:
        tasks.append(
            AgentTask(
                "Logistics",
                "reroute_or_expedite",
                "Find the fastest viable intervention: reroute, expedite, or nearest cold storage.",
            )
        )
    if risk in ("HIGH", "CRITICAL"):
        tasks.append(
            AgentTask(
                "Quality",
                "inspection_and_compliance_log",
                "Flag the batch for inspection and create a compliance note from the prediction and anomalies.",
            )
        )
    if risk in ("MEDIUM", "HIGH", "CRITICAL"):
        tasks.append(
            AgentTask(
                "Notify",
                "customer_and_ops_notification",
                "Prepare dashboard, email, and SMS notification copy using the alert text.",
            )
        )
    return tasks


def template_alert(context: dict[str, Any], tasks: list[AgentTask]) -> str:
    batch = context["batch"]
    prediction = context["prediction"]
    anomalies = context.get("anomalies", [])
    anomaly_text = ", ".join(
        f"{item['severity']} {item['sensorType']} {item['anomalyType']}" for item in anomalies[:5]
    ) or "no anomaly details"
    actions = ", ".join(task.action for task in tasks)
    return (
        f"Batch {batch['batchId']} is at {prediction['riskLevel']} spoilage risk "
        f"({prediction['spoilageProbability']:.1%}) with about "
        f"{prediction['estimatedHoursLeft']:.1f} hours left. "
        f"Detected anomalies: {anomaly_text}. Recommended actions: {actions}."
    )


def build_alert_context(prediction: Any, anomalies: list[Any]) -> dict[str, Any]:
    return {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "batch": {
            "batchId": prediction.batch_id,
            "customerId": prediction.customer_id,
            "deviceId": prediction.device_id,
            "productType": prediction.product_type,
        },
        "prediction": {
            "modelVersion": prediction.model_version,
            "spoilageProbability": prediction.spoilage_probability,
            "riskLevel": prediction.risk_level,
            "estimatedHoursLeft": prediction.estimated_hours_left,
            "confidenceScore": prediction.confidence_score,
            "coldChainBreaks": prediction.cold_chain_breaks,
        },
        "anomalies": [
            {
                "sensorType": anomaly.sensor_type,
                "readingValue": anomaly.reading_value,
                "anomalyType": anomaly.anomaly_type,
                "severity": anomaly.severity,
                "deviationScore": anomaly.deviation_score,
            }
            for anomaly in anomalies
        ],
    }


def _offline_task(task: AgentTask) -> dict[str, Any]:
    return {"agent": task.agent, "status": "fallback", "action": task.action}


def _safe_json(response: Any) -> dict[str, Any]:
    try:
        return response.json()
    except ValueError:
        return {"text": response.text}


def _clean_endpoint(endpoint: str | None) -> str | None:
    if not endpoint:
        return None
    return endpoint.rstrip("/")
