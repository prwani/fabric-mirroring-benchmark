# TPROC-C CDC Workload Plan

HammerDB TPROC-C is the next workload to add when the benchmark needs realistic OLTP write pressure.

## Why TPROC-C

TPROC-H is useful for analytical data generation and query pressure, but it is not a write-heavy workload after the initial build. TPROC-C exercises transactional insert/update/delete paths and is a better source workload for observing Fabric Mirroring under continuous CDC pressure.

## Isolation model

Run TPROC-C in a separate PostgreSQL database or schema from TPROC-H. The validated baseline uses TPROC-H tables in the `tpch` database, including `lineitem`. TPROC-C has a different table set, so keeping it separate avoids corrupting the TPROC-H baseline and makes Fabric table selection clearer.

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
