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

Use the SQL Server TPROC-H HammerDB scripts. They are source-specific workload scripts, while VM/Fabric deployment remains shared.

For Entra-only tenants, grant the benchmark VM managed identity access to Azure SQL and use HammerDB's SQL Server Entra/MSI mode:

```bash
export AZURE_SQL_AUTH_MODE=entra
export AZURE_SQL_MSI_OBJECT_ID="<benchmark-vm-managed-identity-object-id>"
```

HammerDB uses `mssqls_linux_authent=entra` plus `mssqls_msi_object_id=<guid>`, which maps to the ODBC `ActiveDirectoryMsi` authentication mode on Linux.

In the validated benchmark tenant, group-based SQL admin membership did not allow the managed identity to log in to Azure SQL, and a contained database user created from the managed identity SID did not authenticate after the server admin was restored. The working path was to set the VM system-assigned managed identity as the Azure SQL Microsoft Entra admin:

```bash
export AZURE_SQL_SERVER_NAME=sql-fsqlmb-53vwnrvnudnko
export BENCHMARK_VM_NAME=vm-fsqlmb-53vwnrvnudnko
scripts/provision/setup-azure-sql-vm-mi-admin.sh
```

This is acceptable for an isolated benchmark server. For shared or production SQL servers, use a dedicated Entra admin group or a least-privilege contained user once that path is validated in your tenant.

Validate connectivity/schema state with:

```bash
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-check-sqlserver-tproch.tcl
```

```bash
export AZURE_SQL_SQLCMD_ARGS="-C -S $AZURE_SQL_HOST -d $AZURE_SQL_DATABASE -U $AZURE_SQL_ADMIN_USER -P '$AZURE_SQL_ADMIN_PASSWORD'"
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-build-sqlserver-tproch.tcl
```

After the TPROC-H build, create the marker table:

```bash
sqlcmd -C -S "$AZURE_SQL_HOST" -d "$AZURE_SQL_DATABASE" \
  -U "$AZURE_SQL_ADMIN_USER" -P "$AZURE_SQL_ADMIN_PASSWORD" \
  -i scripts/provision/setup-azure-sql-cdc-marker.sql
```

For query workload after mirroring:

```bash
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-run-sqlserver-tproch.tcl
```

## Measurement scripts

The shared measurement scripts can use Azure SQL as the source without duplicating Fabric polling logic:

```bash
python3 scripts/benchmark/measure-initial-sync.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --tables "dbo.region,dbo.nation,dbo.supplier,dbo.customer,dbo.part,dbo.partsupp,dbo.orders,dbo.lineitem,dbo.fabric_cdc_latency_marker"

python3 scripts/benchmark/run-cdc-latency-test.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-marker-table dbo.fabric_cdc_latency_marker
```

## Fabric mirroring tutorial

<https://learn.microsoft.com/fabric/mirroring/azure-sql-database-tutorial>

## Live validation notes

The Sweden Central Azure SQL source was prepared with HammerDB TPROC-H scale factor 1 using VM managed identity authentication:

| Table | Source rows |
|---|---:|
| `dbo.region` | 5 |
| `dbo.nation` | 25 |
| `dbo.supplier` | 10,000 |
| `dbo.customer` | 150,000 |
| `dbo.part` | 200,000 |
| `dbo.partsupp` | 800,000 |
| `dbo.orders` | 1,500,000 |
| `dbo.lineitem` | 6,002,677 |
| `dbo.fabric_cdc_latency_marker` | 0 |

Create the Fabric mirrored Azure SQL Database item in workspace `fsqlmb-benchmark`, connect to `sql-fsqlmb-53vwnrvnudnko.database.windows.net` / `tpch`, and select the tables above. Use Organization Account, service principal, or workspace identity because SQL Basic authentication is blocked when the Azure SQL server is Entra-only.

## Notes

Fabric mirroring for Azure SQL Database requires a supported database tier. This adapter uses vCore General Purpose rather than low-DTU Basic/S0 tiers.

Fabric setup can use Organization Account, service principal, workspace identity, or Basic authentication when the source allows it. The prepared SQL user receives the minimum Fabric permissions documented by Microsoft: `SELECT`, `ALTER ANY EXTERNAL MIRROR`, `VIEW DATABASE PERFORMANCE STATE`, and `VIEW DATABASE SECURITY STATE`.
