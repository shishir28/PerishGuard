-- SensorReadings: raw time-series telemetry from IoT Hub.
-- One row per device reading. Gas/shock/light columns are nullable so devices
-- with different sensor packages can write partial rows.

DROP TABLE IF EXISTS "SensorReadings" CASCADE;

CREATE TABLE "SensorReadings" (
    "ReadingId"     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "BatchId"       TEXT          NOT NULL,
    "CustomerId"    TEXT          NOT NULL,
    "DeviceId"      TEXT          NOT NULL,
    "ProductType"   TEXT          NOT NULL,
    "ReadingAt"     TIMESTAMP(0)  NOT NULL,
    "Temperature"   DOUBLE PRECISION  NULL,
    "Humidity"      DOUBLE PRECISION  NULL,
    "Ethylene"      DOUBLE PRECISION  NULL,
    "CO2"           DOUBLE PRECISION  NULL,
    "NH3"           DOUBLE PRECISION  NULL,
    "VOC"           DOUBLE PRECISION  NULL,
    "ShockG"        DOUBLE PRECISION  NULL,
    "LightLux"      DOUBLE PRECISION  NULL,
    "IngestedAt"    TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE INDEX "IX_SensorReadings_BatchId_ReadingAt"
    ON "SensorReadings" ("BatchId", "ReadingAt");
CREATE INDEX "IX_SensorReadings_CustomerId_ReadingAt"
    ON "SensorReadings" ("CustomerId", "ReadingAt");
CREATE INDEX "IX_SensorReadings_DeviceId_ReadingAt"
    ON "SensorReadings" ("DeviceId", "ReadingAt");
