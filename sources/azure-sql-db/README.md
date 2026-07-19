# Azure SQL Database source adapter

Status: live deployment, Fabric mirroring, initial-snapshot parity, and SQL analytics endpoint validation verified.

## Azure resource

- Azure SQL logical server
- Azure SQL Database using vCore General Purpose (`GP_Gen5_4` by default)
- Source type: `azure-sql-db`
- Microsoft Entra-only authentication by default for policy-compliant deployments
- Optional SQL authentication administrator only when `AZURE_SQL_AAD_ONLY_AUTH=false` and the tenant policy allows it
- System-assigned managed identity on the Azure SQL logical server for Fabric OneLake publishing

This adapter benchmarks one of Fabric Mirroring's **supported operational data sources**. Query the mirrored database through its **SQL analytics endpoint**.

## Network modes

- **Public network (default):** enables Azure SQL public network access and creates firewall rules for the benchmark VM, current client, and Azure services. Use `azuredeploy-azure-sql-db.json`.
- **Private network:** disables Azure SQL public network access and deploys an Azure SQL private endpoint, private DNS zone, and dedicated Fabric VNet data gateway subnet. Use `azuredeploy-azure-sql-db-private.json`, then create the VNet data gateway manually in Fabric/Power BI **Manage connections and gateways**. The subscription must have the `Microsoft.PowerPlatform` provider registered.

## Required parameters

- `SQL_ENTRA_ADMIN_LOGIN`
- `SQL_ENTRA_ADMIN_OBJECT_ID`
- `ADMIN_UPN`
- `CURRENT_CLIENT_IP_ADDRESS` — public IPv4 address in CIDR form, such as `203.0.113.10/32`; find it with `curl -4 ifconfig.me` or https://whatismyipaddress.com/

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

To have the script-based deployment create a new source service principal and assign Directory Readers to the Azure SQL logical-server managed identity, set these optional flags first:

```bash
export ASSIGN_AZURE_SQL_SERVER_DIRECTORY_READERS=true
export PROVISION_FABRIC_SOURCE_APP=true
scripts/provision/deploy-azure.sh
source results/fabric-source-app.env
```

Directory Readers requires a tenant administrator who can assign directory roles. The generated source-app environment file contains a secret, is ignored by Git via `*.env`, and is created with mode `0600`; do not commit or share it. The Deploy-to-Azure template uses the same post-deployment scripts after provisioning infrastructure. For an existing approved Fabric connection, provide `FABRIC_CONNECTION_ID` rather than provisioning another source app.

Copy these deployment outputs into `.env`:

- `AZURE_SQL_HOST=<azureSqlFullyQualifiedDomainName>`
- `AZURE_SQL_DATABASE=<azureSqlDatabaseName>`
- `FABRIC_CAPACITY_ID=<fabricCapacityId>`
- benchmark VM public IP
- `AZURE_SQL_SERVER_PRINCIPAL_ID`

## Prepare Azure SQL Database for mirroring

For the default Entra-only **noninteractive** benchmark-VM path, use ODBC/MSI rather than Linux `sqlcmd -G`:

```bash
python3 scripts/provision/run-azure-sql-msi.py \
  --file scripts/provision/setup-azure-sql-entra-mirroring-prereqs.sql
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

For a Fabric service-principal connection, the Azure SQL server managed identity needs Directory Readers before it can resolve the app while creating its server login. Create the server login in `master` first, then map the database user and grant permissions:

```bash
python3 scripts/provision/grant-azure-sql-master-entra-principal-msi.py
python3 scripts/provision/grant-azure-sql-fabric-entra-principal-msi.py
```

The first helper runs `CREATE LOGIN ... FROM EXTERNAL PROVIDER`; the second maps `CREATE USER ... FOR LOGIN` and grants the mirroring permissions. For an Organizational account or group, set `FABRIC_ENTRA_PRINCIPAL`, `FABRIC_ENTRA_OBJECT_ID`, and `FABRIC_ENTRA_PRINCIPAL_TYPE`, then use the same login-to-user flow. Set `FABRIC_REPLACE_CONTAINED_USER=true` only when intentionally replacing a benchmark-owned mapped user.

`AZURE_SQL_SQLCMD_ARGS` is the full source Azure SQL `sqlcmd` argument string; `FABRIC_SQLCMD_ARGS` is the equivalent target SQL analytics endpoint string written by `setup-fabric-items.py`. On Linux, `sqlcmd -G` authenticates an Entra user and does not use the VM managed identity. Use it only interactively. Noninteractive validation uses ODBC/MSI for both paths: the source MSI runner above and the target Fabric ODBC access-token path after assigning the VM identity Fabric Viewer.

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
python3 scripts/provision/run-azure-sql-msi.py \
  --file scripts/provision/setup-tprocc-benchmark-columns-azure-sql.sql
```

Create the marker table after the HammerDB build and before mirroring:

```bash
python3 scripts/provision/setup-azure-sql-cdc-marker-msi.py
```

`dbo.fabric_cdc_latency_marker` is benchmark-owned. It has `marker_id uniqueidentifier` as its primary key plus `batch_id`, `operation_type`, `source_send_ts`, `source_commit_ts`, and optional `payload`. A controlled source insert is timestamped and then matched by `marker_id` at the SQL analytics endpoint. This is a CDC visibility boundary after mirroring has started; it does not measure initial snapshot loading, schema discovery, or internal replication time.

## Provision Fabric mirroring through the public API

For the public Azure SQL path, do not manually create the mirror in the portal. Run the same post-deployment script after either Deploy-to-Azure or CLI infrastructure provisioning:

```bash
export SOURCE_TYPE=azure-sql-db
export FABRIC_CREATE_CONNECTION=true # omit when FABRIC_CONNECTION_ID is already set
export FABRIC_GRANT_BENCHMARK_VM_WORKSPACE_VIEWER=true
python3 scripts/provision/setup-fabric-items.py
source results/fabric-mirror-setup.env
```

The script creates or reuses the workspace, source connection, mirrored database, and SQL analytics endpoint. `FABRIC_MIRROR_TABLES` selects the default TPROC-C tables plus the marker; leave it empty to mirror all data. The private-network path additionally needs a manually created VNet data gateway before this script runs.

After Fabric mirroring is configured for the `tprocc` database, run:

```bash
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-run-sqlserver-tprocc.tcl
```

## Measurement scripts

The shared measurement scripts can use Azure SQL as the source without duplicating SQL analytics endpoint polling logic. The first command measures **initial snapshot parity**, not CDC:

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

CDC begins only after initial snapshot parity succeeds. The marker command measures post-start commits becoming visible at the SQL analytics endpoint.

For post-mirroring schema evolution, add a benchmark column to the smaller `dbo.warehouse` table instead of `dbo.stock`:

```bash
python3 scripts/provision/run-azure-sql-msi.py \
  --file scripts/provision/setup-tprocc-schema-evolution-azure-sql.sql
```

If the mirrored database item is configured to add new tables automatically, test that path with:

```bash
python3 scripts/benchmark/run-new-table-auto-replication-test.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --rows 1000
```

After initial setup or a schema/table-selection change, refresh endpoint metadata before validating the resulting tables or columns:

```bash
python3 scripts/benchmark/refresh-fabric-sql-endpoint-metadata.py
```

Store its output with the run. `NotRun` plus a recent `lastSuccess` is not an error; it means no additional table refresh was needed. Never invoke this metadata refresh while marker-latency polling, because it is a result-consistency step rather than a CDC latency operation.

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

The verified flow creates the Fabric mirrored Azure SQL Database through `setup-fabric-items.py`; it uses an approved Organization Account, service principal, or workspace identity because SQL Basic authentication is blocked when the Azure SQL server is Entra-only.

## Notes

Fabric mirroring for Azure SQL Database requires a supported database tier. This adapter uses vCore General Purpose rather than low-DTU Basic/S0 tiers.

Fabric setup can use Organization Account, service principal, workspace identity, or Basic authentication when the source allows it. The prepared SQL user receives the minimum Fabric permissions documented by Microsoft: `SELECT`, `ALTER ANY EXTERNAL MIRROR`, `VIEW DATABASE PERFORMANCE STATE`, and `VIEW DATABASE SECURITY STATE`.

## References

- [Microsoft Fabric Mirroring overview and supported operational data sources](https://learn.microsoft.com/fabric/mirroring/overview)
- [Tutorial: Mirror Azure SQL Database in Microsoft Fabric](https://learn.microsoft.com/fabric/mirroring/azure-sql-database-tutorial)
- [Fabric Mirroring REST API](https://learn.microsoft.com/fabric/mirroring/mirrored-database-rest-api)
- [Microsoft Entra service principals with Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-service-principal-tutorial)
