# Azure SQL Database source adapter

Status: infrastructure adapter implemented; HammerDB and Fabric mirroring validation pending.

## Azure resource

- Azure SQL logical server
- Azure SQL Database using vCore General Purpose (`GP_Gen5_2`)
- Source type: `azure-sql-db`
- Entra-only authentication

## Required parameters

- `SQL_ENTRA_ADMIN_LOGIN`
- `SQL_ENTRA_ADMIN_OBJECT_ID`

## HammerDB workload

HammerDB supports SQL Server workloads, but this repo uses Entra-only Azure SQL authentication to avoid SQL admin credentials in Bicep. Validate the HammerDB authentication path before claiming benchmark support.

## Fabric mirroring tutorial

<https://learn.microsoft.com/fabric/mirroring/azure-sql-database-tutorial>

## Notes

Fabric mirroring for Azure SQL Database requires a supported database tier. This adapter uses vCore General Purpose rather than low-DTU Basic/S0 tiers.

