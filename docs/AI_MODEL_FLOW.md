# PerishGuard AI Model Flow

This diagram shows where AI and ML models are used in the overall PerishGuard flow.

```mermaid
flowchart TD
    A[IoT sensors / HTTP demo reading] --> B[predict_spoilage / ingest_reading]
    B --> C[Normalize telemetry payload]
    C --> D[Store SensorReadings in PostgreSQL]
    D --> E[Load batch history and customer settings]

    E --> F[Deterministic anomaly detection]
    F --> G[Store AnomalyEvents]
    F --> H[Build shared feature vector]

    H --> I{{ONNX ML models}}
    I --> I1[LightGBM classifier<br/>spoilage probability]
    I --> I2[LightGBM regressor<br/>estimated hours left]

    I1 --> J[Derive risk level from thresholds]
    I2 --> J
    J --> K[Store SpoilagePredictions]

    K --> L{Alert threshold met?}
    L -- No --> M[Dashboard reads updated risk, telemetry, anomalies]
    L -- Yes --> N[nemoclaw_dispatch builds structured alert context]

    N --> O{{Optional Ollama LLM}}
    O --> O1[Generate alert text<br/>and operator guidance]
    N --> O2[Deterministic template fallback]
    O1 --> P[Slack / email / dashboard alert surfaces]
    O2 --> P

    N --> Q{{Optional NemoClaw agents}}
    Q --> Q1[Create logistics / quality / notify tasks]
    Q1 --> R[AlertDispatchLog audit trail]
    P --> R
    R --> M

    M --> S[Dashboard operator workflows]
    S --> T[Batch drill-down]
    T --> U{{Optional Ollama LLM}}
    U --> U1[Explain why the model flagged the batch]
    T --> U2[Deterministic explanation fallback]
    U1 --> V[Explanation + recommended action]
    U2 --> V

    S --> W[Natural-language query panel]
    W --> X{{Optional Ollama LLM}}
    X --> X1[Convert question to guarded SELECT SQL]
    X1 --> Y[Validate SQL guardrails]
    W --> X2[Prebuilt fallback SQL]
    X2 --> Y
    Y --> Z[Execute customer-scoped PostgreSQL query]
    Z --> AA{{Optional Ollama LLM}}
    AA --> AA1[Summarize query results]
    Z --> AA2[Template summary fallback]
    AA1 --> AB[Dashboard answer]
    AA2 --> AB

    S --> AC[Model retraining request]
    AC --> AD[Load PostgreSQL labels + readings]
    AD --> AE{{LightGBM training}}
    AE --> AE1[Train classifier]
    AE --> AE2[Train regressor]
    AE1 --> AF[Export ONNX artifacts]
    AE2 --> AF
    AF --> AG[Write model_metadata.json]
    AG --> AH[Record ModelTrainingRuns]
    AH --> AI[predict_spoilage hot-reloads models on next inference]
    AI --> I
```

## Quick Reading

- **ONNX LightGBM models** are the authoritative scoring layer. They produce spoilage probability and estimated shelf-life hours.
- **Deterministic rules** handle anomaly detection, thresholds, SQL validation, and fallback text.
- **Ollama** is used only for explanation, alert copy, query generation, and summarization.
- **NemoClaw** is used only for optional operational task dispatch after risk has already been calculated.
- **Retraining** updates the LightGBM models and exports fresh ONNX artifacts for the live inference path.

## Responsibility Boundary

| Area | Uses AI/ML? | Responsibility |
|---|---:|---|
| Spoilage prediction | Yes, ONNX LightGBM | Calculate probability and hours left |
| Anomaly detection | No | Apply deterministic sensor rules |
| Alert copy | Optional Ollama | Explain the already-computed risk |
| Batch explanation | Optional Ollama | Explain drivers and recommended action |
| Natural-language queries | Optional Ollama | Convert questions to guarded SQL and summarize rows |
| NemoClaw dispatch | Optional agent system | Create operational tasks from prediction context |
| Retraining | Yes, LightGBM | Train and export new classifier/regressor models |
