# TPROC-C CDC Workload Plan

HammerDB TPROC-C is the next workload to add when the benchmark needs realistic OLTP write pressure.

## Why TPROC-C

TPROC-C exercises transactional insert/update/delete paths and is the benchmark workload for observing Fabric Mirroring under continuous CDC pressure.

## Isolation model

Run TPROC-C in its own PostgreSQL database named `tprocc`. This keeps the source database aligned with the workload being mirrored and makes Fabric table selection clear.

Example TPROC-C tables include:

- `warehouse`
- `district`
- `customer`
- `history`
- `new_order`
- `orders`
- `order_line`
- `item`
- `stock`

## Measurement model

Run three streams at the same time:

1. **HammerDB TPROC-C** for realistic source write pressure.
2. **Marker-table batch inserts/updates** for precise p50/p90/p95/p99 latency.
3. **Fabric/Azure platform telemetry** for table-level replication progress and source resource pressure.

TPROC-C-only latency should be described as observed table-level lag, not exact per-transaction latency, unless the benchmark adds source timestamps or transaction identifiers to workload tables.

## Metrics to capture

| Metric | Source |
|---|---|
| HammerDB TPM/NOPM | HammerDB output |
| PostgreSQL CPU, storage, IOPS, connections, WAL-related metrics | Azure Monitor |
| Fabric table status, processed rows, processed bytes, last sync timestamp | Fabric Mirroring REST API |
| Marker p50/p90/p95/p99 latency | `run-cdc-bulk-test.py` output |
| Row-count lag by table | PostgreSQL queries + Fabric SQL endpoint queries |

## First run proposal

1. Build a small TPROC-C schema in a separate database.
2. Configure Fabric Mirroring for the TPROC-C tables plus `fabric_cdc_latency_marker`.
3. Start HammerDB TPROC-C at low concurrency.
4. Run marker-table bulk insert/update batches in parallel.
5. Capture Fabric table status every 60 seconds.
6. Repeat with higher virtual users only after the low-concurrency run is stable.

## Prepared scripts

The repo includes parameterized HammerDB scripts for PostgreSQL TPROC-C:

```bash
export POSTGRES_HOST="<server>.postgres.database.azure.com"
export POSTGRES_ADMIN_USER=pgadmin
export PGPASSWORD="<postgres-password>"
export TPROC_C_DATABASE=tprocc
export TPROC_C_USER=tprocc
export TPROC_C_PASSWORD="<benchmark-user-password>"
export TPROC_C_WAREHOUSES=10
export TPROC_C_BUILD_VUSERS=4
export TPROC_C_VUSERS=8
export TPROC_C_RAMPUP_MINUTES=2
export TPROC_C_DURATION_MINUTES=10

"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-build-tprocc.tcl
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-check-tprocc.tcl
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-run-tprocc.tcl
```

Create the marker table in the TPROC-C database after the schema build:

```bash
psql "host=$POSTGRES_HOST port=5432 dbname=$TPROC_C_DATABASE user=$POSTGRES_ADMIN_USER sslmode=require" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-tprocc-marker.sql
```

## Fabric mirroring setup

Create a new Fabric mirrored database item for the `tprocc` PostgreSQL database, or add a separate mirroring configuration if your tenant workflow supports it. Select the TPROC-C tables and `public.fabric_cdc_latency_marker`.

Mirror the TPROC-C database and select the TPROC-C tables plus `public.fabric_cdc_latency_marker`.
