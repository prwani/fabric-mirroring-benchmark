# PostgreSQL source adapter

Status: implemented and live deployment validated.

## Azure resource

- Azure Database for PostgreSQL Flexible Server
- Default source type: `postgresql`
- Default SKU: `Standard_D2ds_v5`, `GeneralPurpose`
- Default version: PostgreSQL 16

## HammerDB workload

Use the shared PostgreSQL HammerDB scripts:

- `scripts/benchmark/hammerdb-build-tproch.tcl`
- `scripts/benchmark/hammerdb-run-tproch.tcl`

Default initial load scale factor is `TPROC_H_SCALE_FACTOR=1`.

## Fabric mirroring tutorial

<https://learn.microsoft.com/fabric/mirroring/azure-database-postgresql-tutorial>

## Notes

The template configures `wal_level=logical`, replication slots/senders, system-assigned managed identity, firewall access for Azure services, and firewall access from the benchmark VM.

