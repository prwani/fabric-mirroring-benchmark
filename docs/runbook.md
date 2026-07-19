# Runbook

## 1. Configure defaults

Copy `config/benchmark.env.example` to `.env`.

Important defaults:

- `AZURE_LOCATION=swedencentral`
- `SOURCE_TYPE=postgresql`
- `TPROC_C_WAREHOUSES=10`
- `FABRIC_CAPACITY_SKU=F8`
- `POSTGRES_SKU_TIER=GeneralPurpose`
- `POSTGRES_SKU_NAME=Standard_D2ds_v5`
- `POSTGRES_ENABLE_ENTRA_AUTH=true`

Ten warehouses is the default initial data-load target for TPROC-C. Increase it only after the full run works at 10 warehouses.

For non-PostgreSQL sources, set `SOURCE_TYPE` and read the matching `sources/<source>/README.md` before deployment. The same shared deployment script provisions the benchmark VM, Fabric capacity, networking, and monitoring; only the source adapter changes. PostgreSQL is the only currently live-validated default path.

For Azure SQL Database, use **SQL analytics endpoint** consistently to mean the query endpoint of the mirrored database. `AZURE_SQL_SQLCMD_ARGS` is the complete `sqlcmd` argument string for the source Azure SQL database; `FABRIC_SQLCMD_ARGS` is the corresponding string for the target SQL analytics endpoint. `setup-fabric-items.py` writes the latter to `results/fabric-mirror-setup.env`.

On Linux, `sqlcmd -G` uses an Entra user authentication flow and does not acquire the benchmark VM's managed-identity token. Use it only for an interactive operator session. Noninteractive validation from the benchmark VM uses ODBC/MSI: `run-azure-sql-msi.py` for the source, and the Fabric ODBC access-token path after granting the VM identity Fabric Viewer for the target.

PostgreSQL deployments keep password authentication enabled and enable Microsoft Entra authentication by default. To assign a PostgreSQL Microsoft Entra administrator during deployment, set `POSTGRES_ENTRA_ADMIN_NAME`, `POSTGRES_ENTRA_ADMIN_OBJECT_ID`, and optionally `POSTGRES_ENTRA_ADMIN_PRINCIPAL_TYPE`.

## 2. Deploy Azure resources

Preferred reader path after this repo is published:

1. Click the **Deploy to Azure** button in `README.md`.
2. For Azure SQL Database, choose the **public network** template for the simplest baseline, or the **private network** template when Azure SQL public endpoints are prohibited.
3. Fill in the parameters in the Azure Portal. `adminSshPublicKey` is your VM SSH public key; see [Create and use an SSH public-private key pair for Linux VMs in Azure](https://learn.microsoft.com/en-us/azure/virtual-machines/ssh-keys-portal). `currentClientIpAddress` is your public IPv4 address in CIDR form, such as `203.0.113.10/32`. Find it with `curl -4 ifconfig.me` or [WhatIsMyIPAddress.com](https://whatismyipaddress.com/). Azure SQL Entra admin and Fabric capacity admin default to the signed-in deploying user; override them only when a different user or group should administer those resources.
4. Deploy the template.
5. Copy deployment outputs into `.env`.

The Deploy-to-Azure template and the CLI deployment converge on the same post-deployment scripts below. For the public Azure SQL path, use those scripts to create the connection and mirrored database through the public API; do not manually create a mirror in the Fabric portal.

### Private-network Azure SQL mode

The private-network template disables Azure SQL public network access and deploys an Azure SQL private endpoint, private DNS zone, and a dedicated Fabric gateway subnet. Before creating the gateway, a subscription owner must register `Microsoft.PowerPlatform`.

1. In Fabric or Power BI, open **Manage connections and gateways** and create a **Virtual network (VNet) data gateway**.
2. Select the deployment resource group, VNet, and the subnet identified by the `fabricGatewaySubnetId` deployment output.
3. When creating the mirrored Azure SQL Database connection, select that VNet data gateway instead of **None**.

The VNet data gateway is a Fabric-managed resource and cannot currently be created by the ARM/Bicep template. Sweden Central supports VNet data gateways.

CLI path for local development:

```bash
scripts/provision/deploy-azure.sh
```

To select a non-default source through the CLI:

```bash
SOURCE_TYPE=mysql scripts/provision/deploy-azure.sh
```

Azure SQL Database example:

```bash
SOURCE_TYPE=azure-sql-db \
AZURE_RESOURCE_GROUP=rg-fabric-sqldb-mirror-bench \
PROJECT_NAME=fsqlmb \
scripts/provision/deploy-azure.sh
```

Azure SQL Database defaults to Microsoft Entra-only authentication because many enterprise tenants deny SQL authentication on Azure SQL. Set `SQL_ENTRA_ADMIN_LOGIN` and `SQL_ENTRA_ADMIN_OBJECT_ID`. Only set `AZURE_SQL_AAD_ONLY_AUTH=false` when your tenant policy explicitly allows SQL authentication.

When creating a new Fabric service-principal connection, the CLI deployment can provision its source app and assign Directory Readers to the Azure SQL logical-server managed identity:

```bash
export ASSIGN_AZURE_SQL_SERVER_DIRECTORY_READERS=true
export PROVISION_FABRIC_SOURCE_APP=true
SOURCE_TYPE=azure-sql-db scripts/provision/deploy-azure.sh
source results/fabric-source-app.env
```

This option requires a tenant administrator who can assign directory roles. The source-app file contains a client secret, is ignored through the repository `*.env` rule, and is created with `0600` permissions. Do not commit, copy, or broadly source it. The Deploy-to-Azure path uses the same post-deployment scripts after template deployment; set the equivalent values in the protected session before running them.

For Entra-only HammerDB runs from the benchmark VM, set the VM managed identity as the Azure SQL Microsoft Entra admin for the isolated benchmark server:

```bash
export AZURE_SQL_SERVER_NAME="<deployment-output azureSqlServerName>"
export BENCHMARK_VM_NAME="<deployment-output benchmarkVmName>"
scripts/provision/setup-azure-sql-vm-mi-admin.sh
```

Then set:

```bash
export AZURE_SQL_AUTH_MODE=entra
export AZURE_SQL_MSI_OBJECT_ID="<benchmark VM principalId>"
```

For a Fabric service-principal connection, first use Directory Readers on the **Azure SQL server managed identity** so Azure SQL can resolve the service principal. Then create the service-principal server login in `master` and the mapped database user with mirroring grants:

```bash
python3 scripts/provision/grant-azure-sql-master-entra-principal-msi.py
python3 scripts/provision/grant-azure-sql-fabric-entra-principal-msi.py
```

The first helper creates `CREATE LOGIN ... FROM EXTERNAL PROVIDER` and the second maps it with `CREATE USER ... FOR LOGIN`, then grants `SELECT`, `ALTER ANY EXTERNAL MIRROR`, `VIEW DATABASE PERFORMANCE STATE`, and `VIEW DATABASE SECURITY STATE`. For an Organizational account or group, set `FABRIC_ENTRA_PRINCIPAL`, `FABRIC_ENTRA_OBJECT_ID`, and `FABRIC_ENTRA_PRINCIPAL_TYPE` and use the same two-step flow. `FABRIC_REPLACE_CONTAINED_USER=true` is only for a benchmark-owned mapped user.

Record deployment outputs in `.env`, especially:

- `POSTGRES_HOST`
- `POSTGRES_SERVER_NAME`
- `FABRIC_CAPACITY_ID`
- benchmark VM public IP
- for Azure SQL Database: `AZURE_SQL_HOST`, `AZURE_SQL_DATABASE=tprocc`, `AZURE_SQL_MSI_OBJECT_ID`, and `AZURE_SQL_SQLCMD_ARGS`
- for the mirrored database: `FABRIC_SQL_ANALYTICS_ENDPOINT_ID` and `FABRIC_SQLCMD_ARGS`

## 3. Prepare the source database

Follow the relevant source adapter docs:

- `sources/postgresql/README.md`
- `sources/mysql/README.md`
- `sources/azure-sql-db/README.md`
- `sources/sql-mi/README.md`
- `sources/sql-server/README.md`

PostgreSQL-specific setup:

Run the SQL prerequisites before the HammerDB build:

```bash
export PGPASSWORD="$POSTGRES_ADMIN_PASSWORD"
psql "host=$POSTGRES_HOST port=5432 dbname=$POSTGRES_DATABASE user=$POSTGRES_ADMIN_USER sslmode=require" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-postgres-mirroring-prereqs.sql
```

Validate settings, extensions, primary keys, and replication slots:

```bash
scripts/provision/validate-postgres-mirroring.sh
```

If `wal_level` or extension allow-list settings changed, restart PostgreSQL before loading data.

Azure SQL Database-specific setup:

For the default Entra-only, noninteractive VM path, use the ODBC/MSI runner rather than Linux `sqlcmd -G`:

```bash
python3 scripts/provision/run-azure-sql-msi.py \
  --file scripts/provision/setup-azure-sql-entra-mirroring-prereqs.sql
```

SQL-auth path for tenants that allow it:

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

## 4. Install HammerDB

SSH to the benchmark VM, clone or copy this repo, then run:

```bash
scripts/provision/install-hammerdb.sh
```

Set `HAMMERDB_CLI` if `hammerdbcli` is not on `PATH`.

## 5. Build TPROC-C data

For PostgreSQL:

```bash
export TPROC_C_DATABASE=tprocc
export TPROC_C_USER=tprocc
export TPROC_C_PASSWORD="<benchmark-user-password>"
export TPROC_C_WAREHOUSES=10
export TPROC_C_BUILD_VUSERS=4

"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-build-tprocc.tcl
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-check-tprocc.tcl
```

For Azure SQL Database:

```bash
export AZURE_SQL_TPROC_C_DATABASE=tprocc
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-build-sqlserver-tprocc.tcl
```

In Entra-only deployments that use VM managed identity, validate the Azure SQL build with row counts through the same MSI connection path. HammerDB `checkschema` may try to connect to `tempdb`, which is not a reliable readiness check for Azure SQL Database with this authentication mode.

After load, rerun the source validation. Fabric mirroring requires source-specific prerequisites; for relational benchmark tables, primary keys are required for the current PostgreSQL marker/table parity workflow.

Create benchmark-owned columns on `stock` after the HammerDB schema build and before Fabric mirroring. These columns are intentionally present during the first replication attempt so the large-update scenario does not depend on post-mirroring schema changes:

```bash
psql "host=$POSTGRES_HOST port=5432 dbname=$POSTGRES_DATABASE user=$POSTGRES_ADMIN_USER sslmode=require" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-tprocc-benchmark-columns-postgres.sql
```

For Azure SQL Database:

```bash
python3 scripts/provision/run-azure-sql-msi.py \
  --file scripts/provision/setup-tprocc-benchmark-columns-azure-sql.sql
```

Create the CDC marker table after the HammerDB schema build. HammerDB requires an empty target database, so do not create the marker table before the TPROC-C build:

```bash
psql "host=$POSTGRES_HOST port=5432 dbname=$POSTGRES_DATABASE user=$POSTGRES_ADMIN_USER sslmode=require" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-cdc-marker.sql
```

For Azure SQL Database, create the marker table in the `tprocc` database:

```bash
python3 -m pip install pyodbc
python3 scripts/provision/setup-azure-sql-cdc-marker-msi.py
```

The Azure SQL marker schema is `dbo.fabric_cdc_latency_marker(marker_id uniqueidentifier primary key, batch_id nvarchar(100), operation_type nvarchar(20), source_send_ts datetime2(7), source_commit_ts datetime2(7), payload nvarchar(max))`. It is a benchmark-owned boundary table: controlled inserts are timestamped at the source and the same `marker_id` is polled at the SQL analytics endpoint. It measures CDC visibility only after mirroring starts, not the initial snapshot, schema discovery, or Fabric internal replication time.

## 6. Set up Fabric mirroring through the public API

```bash
export FABRIC_CAPACITY_ID="<deployment-output>"
export SOURCE_TYPE=azure-sql-db
scripts/provision/setup-fabric-items.py
source results/fabric-mirror-setup.env
```

For a new source app connection, set `FABRIC_CREATE_CONNECTION=true`; otherwise provide the approved `FABRIC_CONNECTION_ID`. The script creates or reuses the workspace, connection, and mirrored database, starts mirroring, waits for the SQL analytics endpoint, and records its ID and connection settings. `FABRIC_MIRROR_TABLES` selects the `dbo` TPROC-C tables plus `dbo.fabric_cdc_latency_marker`; leave it empty to mirror all data. Confirm that `dbo.stock` includes the benchmark-owned update columns before starting mirroring.

For the private-network template, create the VNet data gateway as described above before running this script. This is the only interactive Fabric resource in the documented path; it is not manual mirror creation.

Record:

- Workspace ID
- Mirrored database item ID
- SQL analytics endpoint details as `FABRIC_SQLCMD_ARGS`

## 7. Measure the initial snapshot

The initial snapshot copies the selected source state into the mirrored database. Start mirroring and record the UTC timestamp. Use Fabric monitoring status/API to identify completion, then confirm row-count parity between the source and SQL analytics endpoint for all selected tables. Do not treat initial-snapshot timing as CDC latency.

Poll row-count parity with:

```bash
python3 scripts/benchmark/measure-initial-sync.py \
  --pg-conn "$POSTGRES_PSQL_CONN" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS"
```

For Azure SQL Database:

```bash
python3 scripts/benchmark/measure-initial-sync.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --tables "dbo.warehouse,dbo.district,dbo.customer,dbo.history,dbo.orders,dbo.new_order,dbo.order_line,dbo.stock,dbo.item,dbo.fabric_cdc_latency_marker"
```

Store raw observations under `results/`.

## 8. Measure CDC latency

CDC measurements begin only after initial snapshot parity succeeds. They measure post-start source commits becoming queryable at the SQL analytics endpoint.

Run source load:

```bash
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-run-tprocc.tcl
```

For Azure SQL Database:

```bash
export AZURE_SQL_AUTH_MODE=entra
export AZURE_SQL_MSI_OBJECT_ID="<benchmark-vm-managed-identity-object-id>"
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-run-sqlserver-tprocc.tcl
```

Then run controlled marker measurement:

```bash
python3 scripts/benchmark/run-cdc-latency-test.py \
  --pg-conn "$POSTGRES_PSQL_CONN" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-marker-table "$FABRIC_MARKER_TABLE"
```

For Azure SQL Database:

```bash
python3 scripts/benchmark/run-cdc-latency-test.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-marker-table dbo.fabric_cdc_latency_marker
```

For larger insert/update batches, run the bulk CDC test. This measures when the entire batch is visible in Fabric and records latency from both first and last source commit timestamps:

```bash
python3 scripts/benchmark/run-cdc-bulk-test.py \
  --pg-conn "$POSTGRES_PSQL_CONN" \
  --operation insert \
  --batch-size 500 \
  --batches 3 \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-marker-table "$FABRIC_MARKER_TABLE"
```

To test updates, the script first seeds mirrored marker rows, waits for the seed batch to appear in Fabric, then updates those rows and measures update visibility:

```bash
python3 scripts/benchmark/run-cdc-bulk-test.py \
  --pg-conn "$POSTGRES_PSQL_CONN" \
  --operation update \
  --batch-size 500 \
  --batches 3 \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-marker-table "$FABRIC_MARKER_TABLE"
```

For the large transactional update scenario, update the TPROC-C `stock` table instead of a separate analytical table. At the default 10 warehouses, `stock` contains 1,000,000 rows. Start with 100,000 rows, then increase to 500,000 or 1,000,000 after the smaller run completes:

```bash
python3 scripts/benchmark/run-stock-bulk-update.py \
  --pg-conn "$POSTGRES_PSQL_CONN" \
  --batch-size 100000 \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-stock-table "_public.stock"
```

For Azure SQL Database:

```bash
python3 scripts/benchmark/run-stock-bulk-update.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --batch-size 100000 \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-stock-table "dbo.stock"
```

To test post-mirroring schema evolution, add a benchmark column to a small TPROC-C table rather than `stock`. TPROC-C does not have a `region` table, so use `warehouse`:

```bash
psql "host=$POSTGRES_HOST port=5432 dbname=$POSTGRES_DATABASE user=$POSTGRES_ADMIN_USER sslmode=require" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-tprocc-schema-evolution-postgres.sql

python3 scripts/benchmark/check-fabric-table-schema.py \
  --schema _public \
  --table warehouse \
  --columns mirror_schema_evolution_note
```

For Azure SQL Database:

```bash
python3 scripts/provision/run-azure-sql-msi.py \
  --file scripts/provision/setup-tprocc-schema-evolution-azure-sql.sql

python3 scripts/benchmark/check-fabric-table-schema.py \
  --schema dbo \
  --table warehouse \
  --columns mirror_schema_evolution_note
```

After initial setup or a schema/table-selection change, refresh SQL analytics endpoint metadata before validating the resulting tables or columns:

```bash
python3 scripts/benchmark/refresh-fabric-sql-endpoint-metadata.py
```

Keep the JSON result with the run. A table status of `NotRun` with a recent `lastSuccess` is not an error: no additional metadata refresh was needed for that table. Do not call this API while marker-latency polling; it is a result-consistency step, not part of the CDC latency path.

If mirroring was configured with **add any new tables to replication**, create a new source table after mirroring starts and measure how long it takes Fabric to auto-add and replicate it:

```bash
python3 scripts/benchmark/run-new-table-auto-replication-test.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --rows 1000
```

For noninteractive validation, use ODBC/MSI on both paths. The source uses `run-azure-sql-msi.py`; for the target, grant the benchmark VM identity Fabric Viewer, sign Azure CLI in with that identity, and use the Fabric ODBC access-token path:

```bash
python3 -m pip install 'pyodbc'
az login --identity
export FABRIC_ACCESS_TOKEN_COMMAND='az account get-access-token --resource https://database.windows.net/ --query accessToken -o tsv'

python3 scripts/benchmark/run-cdc-bulk-test.py \
  --pg-conn "$POSTGRES_PSQL_CONN" \
  --operation insert \
  --batch-size 500 \
  --batches 3 \
  --fabric-odbc-server "$FABRIC_ODBC_SERVER" \
  --fabric-database "$FABRIC_DATABASE" \
  --fabric-marker-table "$FABRIC_MARKER_TABLE"
```

Capture PostgreSQL platform metrics during the same window:

```bash
scripts/benchmark/capture-platform-metrics.sh
```

If Fabric exposes mirroring latency/status metrics through the UI/API in your tenant, export or screenshot those values and save them with the run results.

Capture Fabric table-level status snapshots during long-running tests:

```bash
python3 scripts/benchmark/capture-fabric-mirroring-status.py \
  --workspace-id "$FABRIC_WORKSPACE_ID" \
  --mirrored-database-id "$FABRIC_MIRRORED_DATABASE_ID" \
  --output results/fabric-mirroring-status.json
```

## 9. Summarize results

```bash
python3 scripts/analysis/summarize-results.py \
  --cdc results/cdc-latency.csv \
  --output results/summary.json
```

## 10. Cleanup

Stop/delete Fabric mirroring first, then verify/drop orphaned replication slots in PostgreSQL. Only then delete Azure resources:

```bash
scripts/provision/teardown-azure.sh
```

## 11. Blog post

Before writing the blog, confirm the **Deploy to Azure** button has been tested from the published repo and the Azure deployment succeeds. Write the blog only after both the agent and user have tested every repo step successfully with live Azure and Fabric resources.

Include this short activity split in the blog:

| AI agent activity | Human activity |
|---|---|
| Deploy Azure infrastructure, configure PostgreSQL prerequisites, run HammerDB load, collect metrics, summarize results | Authorize required tenant/API permissions, review results, approve final blog |

## References

- [Microsoft Fabric Mirroring overview and supported operational data sources](https://learn.microsoft.com/fabric/mirroring/overview)
- [Tutorial: Mirror Azure SQL Database in Microsoft Fabric](https://learn.microsoft.com/fabric/mirroring/azure-sql-database-tutorial)
- [Fabric Mirroring REST API](https://learn.microsoft.com/fabric/mirroring/mirrored-database-rest-api)
- [Microsoft Entra service principals with Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-service-principal-tutorial)
