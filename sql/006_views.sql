-- vw_BatchRiskSummary: latest prediction per batch joined with label metadata.
-- Used by the customer dashboard.

CREATE OR REPLACE VIEW "vw_BatchRiskSummary" AS
WITH "LatestPrediction" AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (PARTITION BY p."BatchId" ORDER BY p."PredictedAt" DESC) AS rn
    FROM "SpoilagePredictions" p
)
SELECT
    l."BatchId",
    l."CustomerId",
    l."ProductType",
    l."Origin",
    l."Destination",
    l."Carrier",
    l."PackagingType",
    l."SupplierId",
    l."PackagedAt",
    l."ExpiresAt",
    l."ActualSpoilageAt",
    l."WasSpoiled",
    l."SpoilageType",
    l."QualityScore",
    lp."PredictedAt"          AS "LastPredictedAt",
    lp."SpoilageProbability",
    lp."RiskLevel",
    lp."EstimatedHoursLeft",
    lp."ConfidenceScore",
    lp."ColdChainBreaks",
    lp."AlertSent",
    lp."AlertSentAt",
    lp."AlertChannel"
FROM "SpoilageLabels" l
LEFT JOIN "LatestPrediction" lp
    ON lp."BatchId" = l."BatchId" AND lp.rn = 1;
