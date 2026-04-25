-- Model-performance views for dashboard trust and evaluation reporting.

CREATE OR REPLACE VIEW "vw_ModelPredictionTruth" AS
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
    l."PackagedAt",
    l."ExpiresAt",
    l."ActualSpoilageAt",
    l."WasSpoiled",
    lp."PredictionId",
    lp."PredictedAt" AS "LastPredictedAt",
    lp."SpoilageProbability",
    lp."RiskLevel",
    lp."EstimatedHoursLeft",
    CASE
        WHEN lp."PredictionId" IS NULL THEN NULL
        WHEN lp."SpoilageProbability" >= 0.50 THEN 1
        ELSE 0
    END AS "PredictedSpoiled",
    CASE
        WHEN lp."PredictionId" IS NULL THEN 'UNPREDICTED'
        WHEN l."WasSpoiled" = 1 AND lp."SpoilageProbability" >= 0.50 THEN 'TRUE_POSITIVE'
        WHEN l."WasSpoiled" = 0 AND lp."SpoilageProbability" >= 0.50 THEN 'FALSE_POSITIVE'
        WHEN l."WasSpoiled" = 0 AND lp."SpoilageProbability" < 0.50 THEN 'TRUE_NEGATIVE'
        ELSE 'FALSE_NEGATIVE'
    END AS "OutcomeLabel",
    CASE
        WHEN lp."PredictionId" IS NULL THEN NULL
        ELSE ABS(lp."SpoilageProbability" - l."WasSpoiled"::DOUBLE PRECISION)
    END AS "AbsoluteError"
FROM "SpoilageLabels" l
LEFT JOIN "LatestPrediction" lp
    ON lp."BatchId" = l."BatchId" AND lp.rn = 1;

CREATE OR REPLACE VIEW "vw_ModelPerformanceSummary" AS
SELECT
    "CustomerId",
    "ProductType",
    COUNT(*) AS "EvaluatedBatchCount",
    SUM(CASE WHEN "WasSpoiled" = 1 THEN 1 ELSE 0 END) AS "SpoiledBatchCount",
    AVG("SpoilageProbability") AS "AverageSpoilageProbability",
    AVG(CASE WHEN "WasSpoiled" = 1 THEN "SpoilageProbability" END) AS "AverageProbabilityWhenSpoiled",
    AVG(CASE WHEN "WasSpoiled" = 0 THEN "SpoilageProbability" END) AS "AverageProbabilityWhenFresh",
    AVG("AbsoluteError") AS "MeanAbsoluteError",
    SUM(CASE WHEN "OutcomeLabel" = 'TRUE_POSITIVE' THEN 1 ELSE 0 END) AS "TruePositiveCount",
    SUM(CASE WHEN "OutcomeLabel" = 'FALSE_POSITIVE' THEN 1 ELSE 0 END) AS "FalsePositiveCount",
    SUM(CASE WHEN "OutcomeLabel" = 'TRUE_NEGATIVE' THEN 1 ELSE 0 END) AS "TrueNegativeCount",
    SUM(CASE WHEN "OutcomeLabel" = 'FALSE_NEGATIVE' THEN 1 ELSE 0 END) AS "FalseNegativeCount",
    AVG(CASE WHEN "PredictedSpoiled" = "WasSpoiled" THEN 1.0 ELSE 0.0 END) AS "Accuracy"
FROM "vw_ModelPredictionTruth"
WHERE "LastPredictedAt" IS NOT NULL
GROUP BY "CustomerId", "ProductType";
