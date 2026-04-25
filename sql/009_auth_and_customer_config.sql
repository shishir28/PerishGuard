-- Lightweight local auth + tenant configuration for dashboard workflows.

CREATE TABLE IF NOT EXISTS "Customers" (
    "CustomerId"    TEXT          NOT NULL PRIMARY KEY,
    "CustomerName"  TEXT          NOT NULL,
    "IsActive"      SMALLINT      NOT NULL DEFAULT 1,
    "CreatedAt"     TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS "AppUsers" (
    "UserId"             TEXT          NOT NULL PRIMARY KEY,
    "Email"              TEXT          NOT NULL UNIQUE,
    "DisplayName"        TEXT          NOT NULL,
    "PasswordHash"       TEXT          NOT NULL,
    "IsAdmin"            SMALLINT      NOT NULL DEFAULT 0,
    "DefaultCustomerId"  TEXT          NULL REFERENCES "Customers" ("CustomerId") ON DELETE SET NULL,
    "CreatedAt"          TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    "UpdatedAt"          TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS "UserCustomerAccess" (
    "UserId"      TEXT          NOT NULL REFERENCES "AppUsers" ("UserId") ON DELETE CASCADE,
    "CustomerId"  TEXT          NOT NULL REFERENCES "Customers" ("CustomerId") ON DELETE CASCADE,
    "CreatedAt"   TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    PRIMARY KEY ("UserId", "CustomerId")
);

CREATE TABLE IF NOT EXISTS "UserSessions" (
    "SessionTokenHash"   TEXT          NOT NULL PRIMARY KEY,
    "UserId"             TEXT          NOT NULL REFERENCES "AppUsers" ("UserId") ON DELETE CASCADE,
    "ActiveCustomerId"   TEXT          NOT NULL REFERENCES "Customers" ("CustomerId") ON DELETE CASCADE,
    "ExpiresAt"          TIMESTAMP(0)  NOT NULL,
    "CreatedAt"          TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    "LastSeenAt"         TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS "CustomerSettings" (
    "CustomerId"       TEXT          NOT NULL PRIMARY KEY REFERENCES "Customers" ("CustomerId") ON DELETE CASCADE,
    "RiskThresholds"   JSONB         NOT NULL DEFAULT '{}'::jsonb,
    "AnomalyConfig"    JSONB         NOT NULL DEFAULT '{}'::jsonb,
    "AlertConfig"      JSONB         NOT NULL DEFAULT '{}'::jsonb,
    "RouteConfig"      JSONB         NOT NULL DEFAULT '{}'::jsonb,
    "UpdatedAt"        TIMESTAMP(0)  NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS "RouteLocations" (
    "LocationName"  TEXT              NOT NULL PRIMARY KEY,
    "Latitude"      DOUBLE PRECISION  NOT NULL,
    "Longitude"     DOUBLE PRECISION  NOT NULL,
    "Region"        TEXT              NULL,
    "CountryCode"   TEXT              NULL
);

CREATE INDEX IF NOT EXISTS "IX_AppUsers_DefaultCustomerId"
    ON "AppUsers" ("DefaultCustomerId");
CREATE INDEX IF NOT EXISTS "IX_UserSessions_UserId_ExpiresAt"
    ON "UserSessions" ("UserId", "ExpiresAt" DESC);
CREATE INDEX IF NOT EXISTS "IX_UserSessions_ActiveCustomerId"
    ON "UserSessions" ("ActiveCustomerId", "ExpiresAt" DESC);
CREATE INDEX IF NOT EXISTS "IX_UserCustomerAccess_CustomerId"
    ON "UserCustomerAccess" ("CustomerId");

INSERT INTO "Customers" ("CustomerId", "CustomerName")
SELECT customer_id, 'Demo Customer ' || customer_id
FROM (
    SELECT 'C' || to_char(n, 'FM000') AS customer_id
    FROM generate_series(0, 11) AS n
) seeded
ON CONFLICT ("CustomerId") DO NOTHING;

INSERT INTO "CustomerSettings" ("CustomerId", "RiskThresholds", "AnomalyConfig", "AlertConfig", "RouteConfig")
SELECT
    c."CustomerId",
    '{"CRITICAL": 0.8, "HIGH": 0.6, "MEDIUM": 0.35}'::jsonb,
    '{
        "humidityWarning": 85,
        "humidityCritical": 90,
        "gasCriticalMultiplier": 1.5,
        "temperatureRateDelta": 2.0,
        "temperatureCriticalDelta": 4.0
    }'::jsonb,
    '{
        "cooldownMinutes": 30,
        "logisticsHoursLeftTrigger": 12,
        "emailEnabled": true,
        "slackEnabled": true
    }'::jsonb,
    '{}'::jsonb
FROM "Customers" c
ON CONFLICT ("CustomerId") DO NOTHING;

INSERT INTO "RouteLocations" ("LocationName", "Latitude", "Longitude", "Region", "CountryCode")
VALUES
    ('Fresno', -36.7378, 119.7871, 'California', 'US'),
    ('Auckland', -36.8509, 174.7645, 'Auckland', 'NZ'),
    ('Osaka', 34.6937, 135.5023, 'Kansai', 'JP'),
    ('Seattle', 47.6062, -122.3321, 'Washington', 'US'),
    ('Rotterdam', 51.9244, 4.4777, 'South Holland', 'NL'),
    ('Valencia', 39.4699, -0.3763, 'Valencian Community', 'ES'),
    ('Sydney', -33.8688, 151.2093, 'New South Wales', 'AU'),
    ('Melbourne', -37.8136, 144.9631, 'Victoria', 'AU'),
    ('Brisbane', -27.4698, 153.0251, 'Queensland', 'AU'),
    ('Perth', -31.9505, 115.8605, 'Western Australia', 'AU'),
    ('Adelaide', -34.9285, 138.6007, 'South Australia', 'AU'),
    ('Canberra', -35.2809, 149.1300, 'Australian Capital Territory', 'AU')
ON CONFLICT ("LocationName") DO NOTHING;

INSERT INTO "AppUsers" ("UserId", "Email", "DisplayName", "PasswordHash", "IsAdmin", "DefaultCustomerId")
VALUES
    (
        'admin',
        'admin@perishguard.local',
        'PerishGuard Admin',
        'pbkdf2_sha256$200000$pgdemo-admin$ZXyPC+4hjKkSS+zzDfdyJvRRoLn9m6W25QpaCdL8lds=',
        1,
        'C010'
    )
ON CONFLICT ("UserId") DO NOTHING;

INSERT INTO "AppUsers" ("UserId", "Email", "DisplayName", "PasswordHash", "IsAdmin", "DefaultCustomerId")
SELECT
    'ops-' || lower(c."CustomerId"),
    'ops+' || lower(c."CustomerId") || '@perishguard.local',
    'Ops ' || c."CustomerId",
    'pbkdf2_sha256$200000$pgdemo-customer$GZNkGBxaCFsxW5K5XzTaXn7G6xztrPFAt2vVOgG51nk=',
    0,
    c."CustomerId"
FROM "Customers" c
ON CONFLICT ("UserId") DO NOTHING;

INSERT INTO "UserCustomerAccess" ("UserId", "CustomerId")
SELECT 'admin', c."CustomerId"
FROM "Customers" c
ON CONFLICT ("UserId", "CustomerId") DO NOTHING;

INSERT INTO "UserCustomerAccess" ("UserId", "CustomerId")
SELECT 'ops-' || lower(c."CustomerId"), c."CustomerId"
FROM "Customers" c
ON CONFLICT ("UserId", "CustomerId") DO NOTHING;
