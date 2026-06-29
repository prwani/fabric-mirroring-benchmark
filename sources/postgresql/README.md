# PostgreSQL source adapter

Status: implemented and live deployment validated.

## Azure resource

- Azure Database for PostgreSQL Flexible Server
- Default source type: `postgresql`
- Default SKU: `Standard_D2ds_v5`, `GeneralPurpose`
- Default version: PostgreSQL 16

## HammerDB workload

Use the PostgreSQL HammerDB TPROC-C scripts:

- `scripts/benchmark/hammerdb-build-tprocc.tcl`
- `scripts/benchmark/hammerdb-check-tprocc.tcl`
- `scripts/benchmark/hammerdb-run-tprocc.tcl`

Default initial load size is `TPROC_C_WAREHOUSES=10`. This creates transactional OLTP-shaped tables and supports a sustained write workload for CDC latency measurements.

## Fabric mirroring tutorial

<https://learn.microsoft.com/fabric/mirroring/azure-database-postgresql-tutorial>

## Notes

The template configures `wal_level=logical`, replication slots/senders, system-assigned managed identity, firewall access for Azure services, and firewall access from the benchmark VM.
