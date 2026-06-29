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

PostgreSQL deployments keep password authentication enabled and enable Microsoft Entra authentication by default. To assign a PostgreSQL Microsoft Entra administrator during deployment, set `POSTGRES_ENTRA_ADMIN_NAME`, `POSTGRES_ENTRA_ADMIN_OBJECT_ID`, and optionally `POSTGRES_ENTRA_ADMIN_PRINCIPAL_TYPE`.

## 2. Deploy Azure resources

Preferred reader path after this repo is published:

1. Click the **Deploy to Azure** button in `README.md`.
2. Fill in the parameters in the Azure Portal.
3. Deploy the template.
4. Copy deployment outputs into `.env`.

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

If Fabric Organizational account authentication is used, the same Entra user or group must exist as a contained user in the benchmark database with mirroring permissions. In tenants where Azure SQL cannot look up Entra users because the SQL server identity lacks Directory Readers, grant by object ID:

```bash
export FABRIC_ENTRA_PRINCIPAL="<UPN or group display name used in Fabric>"
export FABRIC_ENTRA_OBJECT_ID="<Entra object ID>"
export FABRIC_ENTRA_PRINCIPAL_TYPE=E # E=user/app, X=group
python3 scripts/provision/grant-azure-sql-fabric-entra-principal-msi.py
```

Record deployment outputs in `.env`, especially:

- `POSTGRES_HOST`
- `POSTGRES_SERVER_NAME`
- `FABRIC_CAPACITY_ID`
- benchmark VM public IP
- for Azure SQL Database: `AZURE_SQL_HOST`, `AZURE_SQL_DATABASE=tprocc`, `AZURE_SQL_MSI_OBJECT_ID`, and `AZURE_SQL_SQLCMD_ARGS`

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

Default Entra-only path:

```bash
sqlcmd -C -S "$AZURE_SQL_HOST" -d "$AZURE_SQL_DATABASE" -G \
  -v FABRIC_ENTRA_PRINCIPAL="$SQL_ENTRA_ADMIN_LOGIN" \
  -i scripts/provision/setup-azure-sql-entra-mirroring-prereqs.sql
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
sqlcmd $AZURE_SQL_SQLCMD_ARGS \
  -i scripts/provision/setup-tprocc-benchmark-columns-azure-sql.sql
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

## 6. Set up Fabric mirroring

```bash
export FABRIC_CAPACITY_ID="<deployment-output>"
scripts/provision/setup-fabric-items.py
```

Create the mirrored database item for the selected source through one of these supported paths:

- Fabric portal mirroring experience.
- Fabric Mirroring REST API: <https://learn.microsoft.com/fabric/mirroring/mirrored-database-rest-api>
- fabric-cli item commands: <https://microsoft.github.io/fabric-cli/examples/item_examples/#startstop-mirrored-databases>

Select the TPROC-C tables and `public.fabric_cdc_latency_marker`. Confirm that `stock` includes `mirror_benchmark_update_batch`, `mirror_benchmark_update_ts`, and `mirror_benchmark_payload` before starting mirroring.

For Azure SQL Database, create a mirrored Azure SQL Database item and either mirror all data or select the `dbo` TPROC-C tables plus `dbo.fabric_cdc_latency_marker`. Confirm that `dbo.stock` includes `mirror_benchmark_update_batch`, `mirror_benchmark_update_ts`, and `mirror_benchmark_payload` before starting mirroring. The source connection can use Basic authentication with the prepared Fabric SQL login, or another supported Fabric authentication method.
In Entra-only deployments, use Organization Account, service principal, or workspace identity instead of Basic authentication.

For the live Azure SQL validation environment:

| Setting | Value |
|---|---|
| Fabric workspace | `fsqlmb-benchmark` |
| Workspace ID | `ab29dc78-79f1-48ff-bcdd-7df991904572` |
| Azure SQL server | `sql-fsqlmb-53vwnrvnudnko.database.windows.net` |
| Azure SQL database | `tprocc` |
| Azure SQL SKU | `GP_Gen5_4` |
| Tables | `dbo.warehouse`, `dbo.district`, `dbo.customer`, `dbo.history`, `dbo.orders`, `dbo.new_order`, `dbo.order_line`, `dbo.stock`, `dbo.item`, `dbo.fabric_cdc_latency_marker` |

The REST API has two relevant operation groups:

- Mirrored database item CRUD operations.
- Mirroring start/stop and monitoring operations.

The fabric-cli can start and stop synchronization after the mirrored database item exists:

```bash
fab start "<workspace>.Workspace/<mirror>.MirroredDatabase"
fab stop "<workspace>.Workspace/<mirror>.MirroredDatabase"
```

Record:

- Workspace ID
- Mirrored database item ID
- Fabric SQL endpoint details as `FABRIC_SQLCMD_ARGS`

## 7. Measure initial sync

Start mirroring and record the UTC timestamp. Use Fabric monitoring status/API to identify when initial sync completes. Confirm row counts between PostgreSQL and Fabric for all selected tables.

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
sqlcmd $AZURE_SQL_SQLCMD_ARGS \
  -i scripts/provision/setup-tprocc-schema-evolution-azure-sql.sql

python3 scripts/benchmark/check-fabric-table-schema.py \
  --schema dbo \
  --table warehouse \
  --columns mirror_schema_evolution_note
```

If mirroring was configured with **add any new tables to replication**, create a new source table after mirroring starts and measure how long it takes Fabric to auto-add and replicate it:

```bash
python3 scripts/benchmark/run-new-table-auto-replication-test.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --rows 1000
```

If interactive `sqlcmd -G` is not practical, use ODBC token authentication instead:

```bash
python3 -m pip install 'pyodbc'

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
| Deploy Azure infrastructure, configure PostgreSQL prerequisites, run HammerDB load, collect metrics, summarize results | Complete Fabric portal connection/mirroring permission prompts, review results, approve final blog |
