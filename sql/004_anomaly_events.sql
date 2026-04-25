-- AnomalyEvents: per-reading anomaly flags from Task 2.

CREATE TABLE IF NOT EXISTS "AnomalyEvents" (
    "EventId"        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "BatchId"        TEXT          NOT NULL,
    "CustomerId"     TEXT          NOT NULL,
    "DeviceId"       TEXT          NOT NULL,
    "SensorType"     TEXT          NOT NULL,
    "ReadingValue"   DOUBLE PRECISION NOT NULL,
    "BaselineMean"   DOUBLE PRECISION NULL,
    "BaselineStd"    DOUBLE PRECISION NULL,
    "DeviationScore" DOUBLE PRECISION NULL,
    "AnomalyType"    TEXT          NOT NULL,  -- statistical | threshold | rate_of_change | shock | light
    "Severity"       TEXT          NOT NULL,  -- INFO | WARNING | CRITICAL
    "DetectedAt"     TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    "Acknowledged"   SMALLINT      NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS "IX_AnomalyEvents_BatchId_DetectedAt"
    ON "AnomalyEvents" ("BatchId", "DetectedAt" DESC);
CREATE INDEX IF NOT EXISTS "IX_AnomalyEvents_CustomerId_DetectedAt"
    ON "AnomalyEvents" ("CustomerId", "DetectedAt" DESC);
CREATE INDEX IF NOT EXISTS "IX_AnomalyEvents_Severity"
    ON "AnomalyEvents" ("Severity") WHERE "Severity" = 'CRITICAL';
