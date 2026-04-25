-- SpoilagePredictions: inference output. Written by the predict_spoilage
-- Azure Function. RiskLevel is a generated column from SpoilageProbability.

DROP TABLE IF EXISTS "SpoilagePredictions" CASCADE;

CREATE TABLE "SpoilagePredictions" (
    "PredictionId"        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "BatchId"             TEXT          NOT NULL,
    "CustomerId"          TEXT          NOT NULL,
    "DeviceId"            TEXT          NOT NULL,
    "ProductType"         TEXT          NOT NULL,
    "ModelVersion"        TEXT          NOT NULL,
    "PredictedAt"         TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    "SpoilageProbability" DOUBLE PRECISION NOT NULL,
    "RiskLevel"           TEXT          GENERATED ALWAYS AS (
        CASE
            WHEN "SpoilageProbability" >= 0.80 THEN 'CRITICAL'
            WHEN "SpoilageProbability" >= 0.60 THEN 'HIGH'
            WHEN "SpoilageProbability" >= 0.35 THEN 'MEDIUM'
            ELSE 'LOW'
        END
    ) STORED,
    "EstimatedHoursLeft"  DOUBLE PRECISION NULL,
    "ConfidenceScore"     DOUBLE PRECISION NULL,
    -- Feature snapshot at prediction time
    "AvgTempLast1h"       DOUBLE PRECISION NULL,
    "MaxTempLast1h"       DOUBLE PRECISION NULL,
    "TempVariance24h"     DOUBLE PRECISION NULL,
    "ColdChainBreaks"     INTEGER       NOT NULL DEFAULT 0,
    -- Alert bookkeeping (filled by nemoclaw_dispatch)
    "AlertSent"           SMALLINT      NOT NULL DEFAULT 0,
    "AlertSentAt"         TIMESTAMP(0)  NULL,
    "AlertChannel"        TEXT          NULL
);

CREATE INDEX "IX_SpoilagePredictions_BatchId_PredictedAt"
    ON "SpoilagePredictions" ("BatchId", "PredictedAt" DESC);
CREATE INDEX "IX_SpoilagePredictions_CustomerId_PredictedAt"
    ON "SpoilagePredictions" ("CustomerId", "PredictedAt" DESC);
CREATE INDEX "IX_SpoilagePredictions_RiskLevel"
    ON "SpoilagePredictions" ("RiskLevel") WHERE "RiskLevel" IN ('HIGH','CRITICAL');
