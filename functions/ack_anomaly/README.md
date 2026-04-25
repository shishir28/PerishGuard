# ack_anomaly

HTTP Function at `POST /api/anomalies/{eventId}/ack`.

Request body:

```json
{
  "customerId": "C010"
}
```

Behavior:

- Marks the matching `AnomalyEvents` row as acknowledged.
- Rejects missing customer context.
- Returns `404` when the event does not belong to the customer.
