-- AnalyticsReports: output of Task 5 batch analytics.
-- ReportData stores the structured payload as JSONB.

DROP TABLE IF EXISTS "AnalyticsReports" CASCADE;

CREATE TABLE "AnalyticsReports" (
    "ReportId"    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "CustomerId"  TEXT          NULL,
    "ReportType"  TEXT          NOT NULL,  -- route | carrier | packaging | seasonal | vendor
    "GeneratedAt" TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    "PeriodStart" TIMESTAMP(0)  NOT NULL,
    "PeriodEnd"   TIMESTAMP(0)  NOT NULL,
    "ReportData"  JSONB         NOT NULL,
    "Summary"     TEXT          NULL       -- LLM-generated executive summary
);

CREATE INDEX "IX_AnalyticsReports_Type_GeneratedAt"
    ON "AnalyticsReports" ("ReportType", "GeneratedAt" DESC);
CREATE INDEX "IX_AnalyticsReports_Customer_Type_GeneratedAt"
    ON "AnalyticsReports" ("CustomerId", "ReportType", "GeneratedAt" DESC);
