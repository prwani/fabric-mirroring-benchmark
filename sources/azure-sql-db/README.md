# Azure SQL Database source adapter

Status: infrastructure adapter implemented; live deployment and Fabric mirroring validation pending.

## Azure resource

- Azure SQL logical server
- Azure SQL Database using vCore General Purpose (`GP_Gen5_2` by default)
- Source type: `azure-sql-db`
- Microsoft Entra-only authentication by default for policy-compliant deployments
- Optional SQL authentication administrator only when `AZURE_SQL_AAD_ONLY_AUTH=false` and the tenant policy allows it
- System-assigned managed identity on the Azure SQL logical server for Fabric OneLake publishing

## Required parameters

- `SQL_ENTRA_ADMIN_LOGIN`
- `SQL_ENTRA_ADMIN_OBJECT_ID`
- `ADMIN_UPN`
- `OPERATOR_PUBLIC_IP`

Optional:

- `AZURE_SQL_ADMIN_PASSWORD` when `AZURE_SQL_AAD_ONLY_AUTH=false`

## Deploy

Use the shared Azure deployment script. This provisions a new resource group, shared benchmark VM, shared networking, shared Fabric capacity, shared Log Analytics workspace, and only the Azure SQL Database source adapter.

```bash
export SOURCE_TYPE=azure-sql-db
export AZURE_RESOURCE_GROUP=rg-fabric-sqldb-mirror-bench
export PROJECT_NAME=fsqlmb
scripts/provision/deploy-azure.sh
```

Copy these deployment outputs into `.env`:

- `AZURE_SQL_HOST=<azureSqlFullyQualifiedDomainName>`
- `AZURE_SQL_DATABASE=<azureSqlDatabaseName>`
- `FABRIC_CAPACITY_ID=<fabricCapacityId>`
- benchmark VM public IP

## Prepare Azure SQL Database for mirroring

Default Entra-only path:

1. Connect to the database as the configured Microsoft Entra admin.
2. For Fabric Organization Account authentication, use the same Entra principal in Fabric or create/grant a dedicated Entra principal:

```bash
sqlcmd -C -S "$AZURE_SQL_HOST" -d "$AZURE_SQL_DATABASE" -G \
  -v FABRIC_ENTRA_PRINCIPAL="$SQL_ENTRA_ADMIN_LOGIN" \
  -i scripts/provision/setup-azure-sql-entra-mirroring-prereqs.sql
```

If your tenant allows SQL authentication, set `AZURE_SQL_AAD_ONLY_AUTH=false` before deployment. Then create SQL logins in `master`, and users/permissions in the benchmark database:

```bash
sqlcmd -C -S "$AZURE_SQL_HOST" -d master \
  -U "$AZURE_SQL_ADMIN_USER" -P "$AZURE_SQL_ADMIN_PASSWORD" \
  -v FABRIC_SQL_LOGIN="$AZURE_SQL_FABRIC_LOGIN" \
     FABRIC_SQL_PASSWORD="$AZURE_SQL_FABRIC_PASSWORD" \
     HAMMERDB_SQL_LOGIN="$AZURE_SQL_HAMMERDB_LOGIN" \
     HAMMERDB_SQL_PASSWORD="$AZURE_SQL_HAMMERDB_PASSWORD" \
  -i scripts/provision/setup-azure-sql-master.sql

sqlcmd -C -S "$AZURE_SQL_HOST" -d "$AZURE_SQL_DATABASE" \
  -U "$AZURE_SQL_ADMIN_USER" -P "$AZURE_SQL_ADMIN_PASSWORD" \
  -v FABRIC_SQL_LOGIN="$AZURE_SQL_FABRIC_LOGIN" \
     FABRIC_SQL_USER=fabric_user \
     HAMMERDB_SQL_LOGIN="$AZURE_SQL_HAMMERDB_LOGIN" \
     HAMMERDB_SQL_USER="$AZURE_SQL_HAMMERDB_LOGIN" \
  -i scripts/provision/setup-azure-sql-mirroring-prereqs.sql
```

## HammerDB workload

Use **TPROC-C** for Azure SQL mirroring latency tests because Azure SQL Database is most commonly mirrored from an OLTP application source.

For Entra-only tenants, grant the benchmark VM managed identity access to Azure SQL and use HammerDB's SQL Server Entra/MSI mode:

```bash
export AZURE_SQL_AUTH_MODE=entra
export AZURE_SQL_MSI_OBJECT_ID="<benchmark-vm-managed-identity-object-id>"
export AZURE_SQL_TPROC_C_USE_BCP=false
```

HammerDB uses `mssqls_linux_authent=entra` plus `mssqls_msi_object_id=<guid>`, which maps to the ODBC `ActiveDirectoryMsi` authentication mode on Linux.
For Entra-only builds, keep `AZURE_SQL_TPROC_C_USE_BCP=false` because HammerDB's SQL Server BCP load path does not use the VM managed identity in the same way as the ODBC connection path.

In the validated benchmark tenant, group-based SQL admin membership did not allow the managed identity to log in to Azure SQL, and a contained database user created from the managed identity SID did not authenticate after the server admin was restored. The working path was to set the VM system-assigned managed identity as the Azure SQL Microsoft Entra admin:

```bash
export AZURE_SQL_SERVER_NAME=sql-fsqlmb-53vwnrvnudnko
export BENCHMARK_VM_NAME=vm-fsqlmb-53vwnrvnudnko
scripts/provision/setup-azure-sql-vm-mi-admin.sh
```

This is acceptable for an isolated benchmark server. For shared or production SQL servers, use a dedicated Entra admin group or a least-privilege contained user once that path is validated in your tenant.

For the transactional workload, create/use a separate Azure SQL database and run:

```bash
export AZURE_SQL_TPROC_C_DATABASE=tprocc
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-build-sqlserver-tprocc.tcl
```

For Entra-only deployments that use VM managed identity, validate readiness with row counts through the same MSI connection path. HammerDB `checkschema` may attempt to connect to `tempdb`, which can fail even when the `tprocc` schema is valid and queryable.

After the HammerDB build and before Fabric mirroring, add benchmark-owned columns to `dbo.stock` so they are present in the first replication attempt:

```bash
sqlcmd $AZURE_SQL_SQLCMD_ARGS \
  -i scripts/provision/setup-tprocc-benchmark-columns-azure-sql.sql
```

After Fabric mirroring is configured for the `tprocc` database, run:

```bash
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-run-sqlserver-tprocc.tcl
```

## Measurement scripts

The shared measurement scripts can use Azure SQL as the source without duplicating Fabric polling logic:

```bash
python3 scripts/benchmark/measure-initial-sync.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --tables "dbo.warehouse,dbo.district,dbo.customer,dbo.history,dbo.orders,dbo.new_order,dbo.order_line,dbo.stock,dbo.item,dbo.fabric_cdc_latency_marker"

python3 scripts/benchmark/run-cdc-latency-test.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-marker-table dbo.fabric_cdc_latency_marker

python3 scripts/benchmark/run-stock-bulk-update.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --batch-size 100000 \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-stock-table dbo.stock
```

For post-mirroring schema evolution, add a benchmark column to the smaller `dbo.warehouse` table instead of `dbo.stock`:

```bash
sqlcmd $AZURE_SQL_SQLCMD_ARGS \
  -i scripts/provision/setup-tprocc-schema-evolution-azure-sql.sql
```

## Fabric mirroring tutorial

<https://learn.microsoft.com/fabric/mirroring/azure-sql-database-tutorial>

## Live validation notes

The Sweden Central Azure SQL source uses HammerDB TPROC-C with VM managed identity authentication on `GP_Gen5_4`:

| Table | Source rows |
|---|---:|
| `dbo.warehouse` | 10 |
| `dbo.district` | 100 |
| `dbo.item` | 100,000 |
| `dbo.stock` | 1,000,000 |
| `dbo.customer` | 300,000 |
| `dbo.orders` | 300,000 |
| `dbo.order_line` | 3,000,481 |
| `dbo.new_order` | 90,000 |
| `dbo.history` | 300,000 |
| `dbo.fabric_cdc_latency_marker` | 0 |

`dbo.stock` also includes the pre-mirroring benchmark columns `mirror_benchmark_update_batch`, `mirror_benchmark_update_ts`, and `mirror_benchmark_payload`.

Create the Fabric mirrored Azure SQL Database item in workspace `fsqlmb-benchmark`, connect to `sql-fsqlmb-53vwnrvnudnko.database.windows.net` / `tprocc`, and select the tables above. Use Organization Account, service principal, or workspace identity because SQL Basic authentication is blocked when the Azure SQL server is Entra-only.

## Notes

Fabric mirroring for Azure SQL Database requires a supported database tier. This adapter uses vCore General Purpose rather than low-DTU Basic/S0 tiers.

Fabric setup can use Organization Account, service principal, workspace identity, or Basic authentication when the source allows it. The prepared SQL user receives the minimum Fabric permissions documented by Microsoft: `SELECT`, `ALTER ANY EXTERNAL MIRROR`, `VIEW DATABASE PERFORMANCE STATE`, and `VIEW DATABASE SECURITY STATE`.
