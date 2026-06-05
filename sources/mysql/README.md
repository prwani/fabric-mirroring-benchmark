# MySQL source adapter

Status: infrastructure adapter implemented; Fabric mirroring validation pending.

## Azure resource

- Azure Database for MySQL Flexible Server
- Source type: `mysql`
- Default SKU: `Standard_D2ds_v4`, `GeneralPurpose`
- Default version: MySQL 8.0.21

## HammerDB workload

HammerDB supports MySQL-compatible benchmark workflows. Add MySQL-specific TCL scripts before claiming benchmark validation for this adapter.

## Fabric mirroring tutorial

<https://learn.microsoft.com/fabric/mirroring/azure-database-mysql-tutorial>

## Notes

Fabric mirroring for Azure Database for MySQL is preview/tenant-gated. Validate availability in the target tenant and region before running a benchmark.

