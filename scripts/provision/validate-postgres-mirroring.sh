#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

load_env
require_env POSTGRES_HOST
require_env POSTGRES_ADMIN_USER
require_env POSTGRES_DATABASE
require_env PGPASSWORD

psql "host=$POSTGRES_HOST port=${POSTGRES_PORT:-5432} dbname=$POSTGRES_DATABASE user=$POSTGRES_ADMIN_USER sslmode=require" <<'SQL'
SELECT name, setting
FROM pg_settings
WHERE name IN ('wal_level', 'max_replication_slots', 'max_wal_senders', 'shared_preload_libraries')
ORDER BY name;

SELECT extname
FROM pg_extension
WHERE extname IN ('uuid-ossp', 'pg_stat_statements')
ORDER BY extname;

WITH target_tables AS (
  SELECT n.nspname AS schema_name, c.relname AS table_name
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relkind = 'r'
    AND n.nspname IN ('public')
    AND c.relname NOT LIKE 'pg_%'
)
SELECT schema_name, table_name
FROM target_tables t
WHERE NOT EXISTS (
  SELECT 1
  FROM pg_index i
  JOIN pg_class c ON c.oid = i.indrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = t.schema_name
    AND c.relname = t.table_name
    AND i.indisprimary
)
ORDER BY schema_name, table_name;

SELECT slot_name, plugin, slot_type, active, restart_lsn, confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
SQL

echo "Validation query completed. Any rows in the primary-key check must be fixed before mirroring."
