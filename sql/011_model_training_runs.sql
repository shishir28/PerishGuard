-- Model training run history for local retraining + auditability.

CREATE TABLE IF NOT EXISTS "ModelTrainingRuns" (
    "RunId"             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "RequestedByUserId" TEXT          NULL REFERENCES "AppUsers" ("UserId") ON DELETE SET NULL,
    "CustomerId"        TEXT          NULL REFERENCES "Customers" ("CustomerId") ON DELETE SET NULL,
    "Status"            TEXT          NOT NULL, -- queued | running | succeeded | failed
    "StartedAt"         TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    "CompletedAt"       TIMESTAMP(0)  NULL,
    "ModelVersion"      TEXT          NULL,
    "TrainingMetrics"   JSONB         NULL,
    "OutputDir"         TEXT          NULL,
    "ErrorMessage"      TEXT          NULL
);

CREATE INDEX IF NOT EXISTS "IX_ModelTrainingRuns_StartedAt"
    ON "ModelTrainingRuns" ("StartedAt" DESC);
CREATE INDEX IF NOT EXISTS "IX_ModelTrainingRuns_Status_StartedAt"
    ON "ModelTrainingRuns" ("Status", "StartedAt" DESC);
CREATE INDEX IF NOT EXISTS "IX_ModelTrainingRuns_CustomerId_StartedAt"
    ON "ModelTrainingRuns" ("CustomerId", "StartedAt" DESC);
