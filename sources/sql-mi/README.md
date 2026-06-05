# Azure SQL Managed Instance source adapter

Status: experimental high-cost scaffold; validation pending.

## Azure resource

- Azure SQL Managed Instance
- Source type: `sql-mi`
- Entra-only authentication
- Dedicated delegated subnet

## Required parameters

- `SQL_ENTRA_ADMIN_LOGIN`
- `SQL_ENTRA_ADMIN_OBJECT_ID`

## HammerDB workload

HammerDB supports SQL Server workloads. Validate connectivity, authentication, schema build, and mirroring before using this adapter for published results.

## Fabric mirroring tutorial

<https://learn.microsoft.com/fabric/mirroring/azure-sql-managed-instance-tutorial>

## Notes

SQL MI deployments are high cost and can take much longer than PaaS database deployments. Do not use this adapter as the default Deploy to Azure path.

