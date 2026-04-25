-- AlertDispatchLog: per-channel delivery audit trail for prediction alerts.

CREATE TABLE IF NOT EXISTS "AlertDispatchLog" (
    "LogId"           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "PredictionId"    BIGINT        NULL REFERENCES "SpoilagePredictions" ("PredictionId") ON DELETE SET NULL,
    "BatchId"         TEXT          NOT NULL,
    "CustomerId"      TEXT          NOT NULL,
    "Channel"         TEXT          NOT NULL,
    "DeliveryStatus"  TEXT          NOT NULL, -- sent | failed | skipped | suppressed
    "Provider"        TEXT          NULL,
    "Target"          TEXT          NULL,
    "AlertText"       TEXT          NULL,
    "ErrorMessage"    TEXT          NULL,
    "TaskCount"       INTEGER       NOT NULL DEFAULT 0,
    "AttemptedAt"     TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS "IX_AlertDispatchLog_BatchId_AttemptedAt"
    ON "AlertDispatchLog" ("BatchId", "AttemptedAt" DESC);
CREATE INDEX IF NOT EXISTS "IX_AlertDispatchLog_CustomerId_AttemptedAt"
    ON "AlertDispatchLog" ("CustomerId", "AttemptedAt" DESC);
CREATE INDEX IF NOT EXISTS "IX_AlertDispatchLog_PredictionId"
    ON "AlertDispatchLog" ("PredictionId");
