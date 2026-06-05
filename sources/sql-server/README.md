# SQL Server source adapter

Status: experimental Azure VM scaffold; mirroring validation pending.

## Azure resource

- SQL Server Developer edition on Azure VM
- Source type: `sql-server`

## Required parameters

- `SQL_SERVER_VM_ADMIN_USERNAME`
- `SQL_SERVER_VM_ADMIN_PASSWORD`

## HammerDB workload

HammerDB supports SQL Server workloads. Add SQL Server-specific TCL scripts and validate SQL Server Agent, CDC/change feed, and Fabric connectivity before claiming benchmark support.

## Fabric mirroring tutorial

<https://learn.microsoft.com/fabric/mirroring/sql-server-tutorial>

## Notes

Fabric mirroring for SQL Server commonly requires additional setup such as On-premises Data Gateway connectivity and CDC/SQL Server Agent for older SQL Server versions. Treat this adapter as infrastructure scaffolding until the gateway and CDC flow are validated.

