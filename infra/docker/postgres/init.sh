#!/usr/bin/env bash
set -euo pipefail

HOST="${POSTGRES_HOST:-postgres}"
PORT="${POSTGRES_PORT:-5432}"
USER="${POSTGRES_USER:-perishguard}"
PASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
DATABASE="${POSTGRES_DB:-perishguard}"

export PGPASSWORD="${PASSWORD}"

echo "Applying schema to ${HOST}:${PORT}/${DATABASE} as ${USER}..."
for script in /sql/*.sql; do
  echo "Applying ${script}..."
  psql -h "${HOST}" -p "${PORT}" -U "${USER}" -d "${DATABASE}" \
       -v ON_ERROR_STOP=1 -f "${script}"
done

echo "Postgres schema initialization complete."
