-- SpoilageLabels: ground truth from QA inspection.
-- One row per batch. ActualSpoilageAt is NULL for batches that completed
-- shelf life without spoiling.

CREATE TABLE IF NOT EXISTS "SpoilageLabels" (
    "BatchId"          TEXT          NOT NULL PRIMARY KEY,
    "CustomerId"       TEXT          NOT NULL,
    "ProductType"      TEXT          NOT NULL,
    "Origin"           TEXT          NOT NULL,
    "Destination"      TEXT          NOT NULL,
    "Carrier"          TEXT          NOT NULL,
    "PackagingType"    TEXT          NOT NULL,
    "SupplierId"       TEXT          NOT NULL,
    "PackagedAt"       TIMESTAMP(0)  NOT NULL,
    "ExpiresAt"        TIMESTAMP(0)  NOT NULL,
    "ActualSpoilageAt" TIMESTAMP(0)  NULL,
    "WasSpoiled"       SMALLINT      NOT NULL,
    "SpoilageType"     TEXT          NULL,   -- bacterial | mold | oxidation | enzymatic
    "QualityScore"     INTEGER       NULL,   -- 0..100
    "CreatedAt"        TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS "IX_SpoilageLabels_ProductType" ON "SpoilageLabels" ("ProductType");
CREATE INDEX IF NOT EXISTS "IX_SpoilageLabels_CustomerId"  ON "SpoilageLabels" ("CustomerId");
CREATE INDEX IF NOT EXISTS "IX_SpoilageLabels_Route"       ON "SpoilageLabels" ("Origin", "Destination");
CREATE INDEX IF NOT EXISTS "IX_SpoilageLabels_Carrier"     ON "SpoilageLabels" ("Carrier");
