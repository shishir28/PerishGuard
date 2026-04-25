-- Route-level risk summary with coordinates for dashboard map rendering.

CREATE OR REPLACE VIEW "vw_RouteRiskSummary" AS
WITH "LatestPrediction" AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (PARTITION BY p."BatchId" ORDER BY p."PredictedAt" DESC) AS rn
    FROM "SpoilagePredictions" p
)
SELECT
    l."CustomerId",
    l."Origin",
    l."Destination",
    origin."Latitude" AS "OriginLatitude",
    origin."Longitude" AS "OriginLongitude",
    destination."Latitude" AS "DestinationLatitude",
    destination."Longitude" AS "DestinationLongitude",
    COUNT(*) AS "BatchCount",
    AVG(COALESCE(lp."SpoilageProbability", 0.0)) AS "AverageSpoilageProbability",
    AVG(COALESCE(lp."EstimatedHoursLeft", 0.0)) AS "AverageEstimatedHoursLeft",
    SUM(CASE WHEN lp."RiskLevel" = 'CRITICAL' THEN 1 ELSE 0 END) AS "CriticalBatchCount",
    SUM(CASE WHEN lp."RiskLevel" IN ('HIGH', 'CRITICAL') THEN 1 ELSE 0 END) AS "HighRiskBatchCount",
    SUM(CASE WHEN l."WasSpoiled" = 1 THEN 1 ELSE 0 END) AS "SpoiledBatchCount",
    MAX(lp."PredictedAt") AS "LastPredictedAt"
FROM "SpoilageLabels" l
LEFT JOIN "LatestPrediction" lp
    ON lp."BatchId" = l."BatchId" AND lp.rn = 1
LEFT JOIN "RouteLocations" origin
    ON origin."LocationName" = l."Origin"
LEFT JOIN "RouteLocations" destination
    ON destination."LocationName" = l."Destination"
GROUP BY
    l."CustomerId",
    l."Origin",
    l."Destination",
    origin."Latitude",
    origin."Longitude",
    destination."Latitude",
    destination."Longitude";
