"""NemoClaw multi-agent alert dispatch for high-risk batches."""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlsplit

try:
    import requests
except ModuleNotFoundError:
    requests = None


DEFAULT_COOLDOWN_MINUTES = 30
DEFAULT_OLLAMA_MODEL = "llama3.3:70b"
DEFAULT_SMTP_PORT = 587
DEFAULT_EMAIL_SUBJECT_PREFIX = "[PerishGuard]"


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
    deliveries: list["ChannelDelivery"]
    error: str | None = None


@dataclass(frozen=True)
class ChannelDelivery:
    channel: str
    status: str
    provider: str | None
    target: str | None
    error: str | None = None
    counts_as_alert: bool = True

    @property
    def delivered(self) -> bool:
        return self.status == "sent"


class AlertDispatcher:
    def __init__(
        self,
        ollama_endpoint: str | None = None,
        nemoclaw_endpoint: str | None = None,
        slack_webhook_url: str | None = None,
        smtp_host: str | None = None,
        smtp_port: int = DEFAULT_SMTP_PORT,
        smtp_username: str | None = None,
        smtp_password: str | None = None,
        smtp_use_tls: bool = True,
        smtp_use_ssl: bool = False,
        alert_email_from: str | None = None,
        alert_email_to: list[str] | None = None,
        email_subject_prefix: str = DEFAULT_EMAIL_SUBJECT_PREFIX,
        cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
        ollama_model: str = DEFAULT_OLLAMA_MODEL,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.ollama_endpoint = _clean_endpoint(ollama_endpoint)
        self.nemoclaw_endpoint = _clean_endpoint(nemoclaw_endpoint)
        self.slack_webhook_url = slack_webhook_url
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.smtp_use_tls = smtp_use_tls
        self.smtp_use_ssl = smtp_use_ssl
        self.alert_email_from = alert_email_from
        self.alert_email_to = alert_email_to or []
        self.email_subject_prefix = email_subject_prefix
        self.cooldown_minutes = cooldown_minutes
        self.ollama_model = ollama_model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "AlertDispatcher":
        return cls(
            ollama_endpoint=os.getenv("OLLAMA_ENDPOINT"),
            nemoclaw_endpoint=os.getenv("NEMOCLAW_ENDPOINT"),
            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
            smtp_host=os.getenv("SMTP_HOST"),
            smtp_port=int(os.getenv("SMTP_PORT", str(DEFAULT_SMTP_PORT))),
            smtp_username=os.getenv("SMTP_USERNAME"),
            smtp_password=os.getenv("SMTP_PASSWORD"),
            smtp_use_tls=_env_bool("SMTP_USE_TLS", True),
            smtp_use_ssl=_env_bool("SMTP_USE_SSL", False),
            alert_email_from=os.getenv("ALERT_EMAIL_FROM"),
            alert_email_to=_split_csv(os.getenv("ALERT_EMAIL_TO")),
            email_subject_prefix=os.getenv("ALERT_EMAIL_SUBJECT_PREFIX", DEFAULT_EMAIL_SUBJECT_PREFIX),
            cooldown_minutes=int(os.getenv("ALERT_COOLDOWN_MINUTES", str(DEFAULT_COOLDOWN_MINUTES))),
            ollama_model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        )

    def dispatch(self, context: dict[str, Any], alert_config: dict[str, Any] | None = None) -> DispatchResult:
        tasks = agent_tasks_for_prediction(context, alert_config)
        if not tasks:
            return DispatchResult(False, False, None, None, [], [])

        alert_text = self._alert_text(context, tasks)
        task_results, task_delivery = self._dispatch_nemoclaw(context, tasks, alert_text)
        deliveries = [task_delivery] if task_delivery is not None else []
        deliveries.append(self._dispatch_slack(alert_text))
        deliveries.append(self._dispatch_email(context, alert_text))

        successful_alert_channels = [
            delivery.channel
            for delivery in deliveries
            if delivery.counts_as_alert and delivery.delivered
        ]
        error_messages = [delivery.error for delivery in deliveries if delivery.error]
        if not successful_alert_channels and not error_messages:
            error_messages.append("No alert channels are configured")

        return DispatchResult(
            should_alert=True,
            alert_sent=bool(successful_alert_channels),
            channel=",".join(successful_alert_channels) or None,
            alert_text=alert_text,
            tasks=task_results,
            deliveries=deliveries,
            error=" | ".join(error_messages) if error_messages else None,
        )

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
        except (requests.RequestException, ValueError):
            return fallback

    def _dispatch_nemoclaw(
        self,
        context: dict[str, Any],
        tasks: list[AgentTask],
        alert_text: str,
    ) -> tuple[list[dict[str, Any]], ChannelDelivery]:
        if self.nemoclaw_endpoint is None:
            return (
                [_offline_task(task) for task in tasks],
                ChannelDelivery(
                    channel="nemoclaw",
                    status="skipped",
                    provider="nemoclaw",
                    target=None,
                    error="NEMOCLAW_ENDPOINT is not configured",
                    counts_as_alert=False,
                ),
            )
        if requests is None:
            return (
                [_offline_task(task) for task in tasks],
                ChannelDelivery(
                    channel="nemoclaw",
                    status="failed",
                    provider="nemoclaw",
                    target=self.nemoclaw_endpoint,
                    error="requests is unavailable",
                    counts_as_alert=False,
                ),
            )

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
            return (
                sent_tasks,
                ChannelDelivery(
                    channel="nemoclaw",
                    status="sent",
                    provider="nemoclaw",
                    target=self.nemoclaw_endpoint,
                    counts_as_alert=False,
                ),
            )
        except requests.RequestException as exc:
            return (
                sent_tasks or [_offline_task(task) for task in tasks],
                ChannelDelivery(
                    channel="nemoclaw",
                    status="failed",
                    provider="nemoclaw",
                    target=self.nemoclaw_endpoint,
                    error=str(exc),
                    counts_as_alert=False,
                ),
            )

    def _dispatch_slack(self, alert_text: str) -> ChannelDelivery:
        if self.slack_webhook_url is None:
            return ChannelDelivery(
                channel="slack",
                status="skipped",
                provider="slack",
                target=None,
                error="SLACK_WEBHOOK_URL is not configured",
            )
        if requests is None:
            return ChannelDelivery(
                channel="slack",
                status="failed",
                provider="slack",
                target=_safe_target(self.slack_webhook_url),
                error="requests is unavailable",
            )

        try:
            response = requests.post(
                self.slack_webhook_url,
                json={"text": alert_text},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return ChannelDelivery(
                channel="slack",
                status="sent",
                provider="slack",
                target=_safe_target(self.slack_webhook_url),
            )
        except requests.RequestException as exc:
            return ChannelDelivery(
                channel="slack",
                status="failed",
                provider="slack",
                target=_safe_target(self.slack_webhook_url),
                error=str(exc),
            )

    def _dispatch_email(self, context: dict[str, Any], alert_text: str) -> ChannelDelivery:
        if not self.smtp_host or not self.alert_email_from or not self.alert_email_to:
            return ChannelDelivery(
                channel="email",
                status="skipped",
                provider="smtp",
                target=",".join(self.alert_email_to) or None,
                error="SMTP_HOST, ALERT_EMAIL_FROM, and ALERT_EMAIL_TO are required for email alerts",
            )

        message = EmailMessage()
        message["From"] = self.alert_email_from
        message["To"] = ", ".join(self.alert_email_to)
        message["Subject"] = self._email_subject(context)
        message.set_content(self._email_body(context, alert_text))

        try:
            if self.smtp_use_ssl:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=self.timeout_seconds) as smtp:
                    self._login_and_send(smtp, message)
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout_seconds) as smtp:
                    smtp.ehlo()
                    if self.smtp_use_tls:
                        smtp.starttls()
                        smtp.ehlo()
                    self._login_and_send(smtp, message)
            return ChannelDelivery(
                channel="email",
                status="sent",
                provider="smtp",
                target=",".join(self.alert_email_to),
            )
        except (OSError, smtplib.SMTPException) as exc:
            return ChannelDelivery(
                channel="email",
                status="failed",
                provider="smtp",
                target=",".join(self.alert_email_to),
                error=str(exc),
            )

    def _login_and_send(self, smtp: smtplib.SMTP, message: EmailMessage) -> None:
        if self.smtp_username:
            smtp.login(self.smtp_username, self.smtp_password or "")
        smtp.send_message(message)

    def _email_subject(self, context: dict[str, Any]) -> str:
        prediction = context["prediction"]
        batch = context["batch"]
        return (
            f"{self.email_subject_prefix} {prediction['riskLevel']} risk "
            f"for batch {batch['batchId']}"
        )

    def _email_body(self, context: dict[str, Any], alert_text: str) -> str:
        batch = context["batch"]
        prediction = context["prediction"]
        anomalies = context.get("anomalies", [])
        anomaly_lines = [
            f"- {item['severity']} {item['sensorType']} {item['anomalyType']} ({item['readingValue']})"
            for item in anomalies[:5]
        ] or ["- No anomaly details available"]
        return "\n".join(
            [
                alert_text,
                "",
                f"Customer: {batch['customerId']}",
                f"Batch: {batch['batchId']}",
                f"Device: {batch['deviceId']}",
                f"Product: {batch['productType']}",
                f"Risk: {prediction['riskLevel']}",
                f"Spoilage probability: {prediction['spoilageProbability']:.1%}",
                f"Estimated hours left: {prediction['estimatedHoursLeft']:.1f}",
                "",
                "Anomalies:",
                *anomaly_lines,
            ]
        )


def agent_tasks_for_prediction(
    context: dict[str, Any],
    alert_config: dict[str, Any] | None = None,
) -> list[AgentTask]:
    prediction = context["prediction"]
    risk = prediction["riskLevel"]
    hours_left = float(prediction.get("estimatedHoursLeft") or 0.0)
    config = alert_config or {}
    logistics_hours_left_trigger = float(config.get("logisticsHoursLeftTrigger", 12))

    tasks: list[AgentTask] = []
    if risk == "CRITICAL" and hours_left < logistics_hours_left_trigger:
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


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_target(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path[:1]}..."
