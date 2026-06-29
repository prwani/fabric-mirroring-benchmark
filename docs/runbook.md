# Runbook

## 1. Configure defaults

Copy `config/benchmark.env.example` to `.env`.

Important defaults:

- `AZURE_LOCATION=swedencentral`
- `SOURCE_TYPE=postgresql`
- `TPROC_H_SCALE_FACTOR=1`
- `FABRIC_CAPACITY_SKU=F8`
- `POSTGRES_SKU_TIER=GeneralPurpose`
- `POSTGRES_SKU_NAME=Standard_D2ds_v5`
- `POSTGRES_ENABLE_ENTRA_AUTH=true`

Scale factor 1 is the default initial data-load target for TPROC-H. Increase it only after the full run works at SF=1.

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

Record deployment outputs in `.env`, especially:

- `POSTGRES_HOST`
- `POSTGRES_SERVER_NAME`
- `FABRIC_CAPACITY_ID`
- benchmark VM public IP
- for Azure SQL Database: `AZURE_SQL_HOST`, `AZURE_SQL_DATABASE`, and `AZURE_SQL_SQLCMD_ARGS`

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

## 5. Build TPROC-H data

```bash
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-build-tproch.tcl
```

After load, rerun the source validation. Fabric mirroring requires source-specific prerequisites; for relational benchmark tables, primary keys are required for the current PostgreSQL marker/table parity workflow.

Create the CDC marker table after the HammerDB schema build. HammerDB requires an empty target database, so do not create the marker table before the TPROC-H build:

```bash
psql "host=$POSTGRES_HOST port=5432 dbname=$POSTGRES_DATABASE user=$POSTGRES_ADMIN_USER sslmode=require" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-cdc-marker.sql
```

For Azure SQL Database, use:

```bash
sqlcmd -C -S "$AZURE_SQL_HOST" -d "$AZURE_SQL_DATABASE" \
  -U "$AZURE_SQL_ADMIN_USER" -P "$AZURE_SQL_ADMIN_PASSWORD" \
  -i scripts/provision/setup-azure-sql-cdc-marker.sql
```

## 6. Set up Fabric mirroring

```bash
export FABRIC_CAPACITY_ID="<deployment-output>"
scripts/provision/setup-fabric-items.py
```

Create the mirrored database item for Azure Database for PostgreSQL through one of these supported paths:

- Fabric portal mirroring experience.
- Fabric Mirroring REST API: <https://learn.microsoft.com/fabric/mirroring/mirrored-database-rest-api>
- fabric-cli item commands: <https://microsoft.github.io/fabric-cli/examples/item_examples/#startstop-mirrored-databases>

Select the TPROC-H tables and `public.fabric_cdc_latency_marker`.

For Azure SQL Database, create a mirrored Azure SQL Database item and either mirror all data or select the `dbo` TPROC-H tables plus `dbo.fabric_cdc_latency_marker`. The source connection can use Basic authentication with the prepared Fabric SQL login, or another supported Fabric authentication method.
In Entra-only deployments, use Organization Account, service principal, or workspace identity instead of Basic authentication.

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
  --tables "dbo.region,dbo.nation,dbo.supplier,dbo.customer,dbo.part,dbo.partsupp,dbo.orders,dbo.lineitem,dbo.fabric_cdc_latency_marker"
```

Store raw observations under `results/`.

## 8. Measure CDC latency

Run optional source load:

```bash
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-run-tproch.tcl
```

For Azure SQL Database:

```bash
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-run-sqlserver-tproch.tcl
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

Check whether expected schema changes are visible in the Fabric SQL endpoint:

```bash
python3 scripts/benchmark/check-fabric-table-schema.py \
  --server "$FABRIC_ODBC_SERVER" \
  --database "$FABRIC_DATABASE" \
  --schema _public \
  --table lineitem \
  --columns mirror_benchmark_update_batch,mirror_benchmark_update_ts
```

## 9. Measure large-table update impact

HammerDB TPROC-H queries reference the standard TPC-H columns. Adding nullable benchmark-only columns to `lineitem` is safe for the benchmark flow because it does not change existing column names or query semantics. Apply this after the HammerDB build:

```bash
psql "$POSTGRES_PSQL_CONN" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-lineitem-bulk-update.sql
```

Wait until the new columns are visible through the Fabric SQL endpoint, then run a controlled large-table update. Start with 100K rows before attempting 1M rows or the full `lineitem` table:

If the benchmark columns do not appear in Fabric after the PostgreSQL schema change, refresh the table in the Fabric mirroring configuration. In one validation run, Fabric did not automatically pick up the new `lineitem` columns; the table had to be removed from the mirrored table list and then added again. Treat this as an observation to confirm with the Fabric product team before publishing externally. A follow-up small-table test on `region` did pick up two new nullable columns automatically after about one minute, so this behavior might depend on table size, table state, or mirroring refresh timing. After re-adding a table, wait for `getTablesMirroringStatus` to move it from `Initialized` to `Replicating` and for `processedRows` to increase before running the bulk-update measurement.

```bash
python3 scripts/benchmark/run-lineitem-bulk-update.py \
  --pg-conn "$POSTGRES_PSQL_CONN" \
  --rows 100000 \
  --batches 1 \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-lineitem-table "$FABRIC_LINEITEM_TABLE"
```

The output CSV records source update timestamps, Fabric visibility time, latency from first and last updated row, and sample `l_orderkey`/`l_linenumber` values for time-travel validation.

Use Fabric Warehouse time travel to compare before and after values for the sampled row. See `scripts/analysis/fabric-time-travel-lineitem.sql` and replace the placeholders with values from the CSV:

```sql
SELECT l_orderkey, l_linenumber, mirror_benchmark_update_batch, mirror_benchmark_update_ts
FROM [_public].[lineitem]
WHERE l_orderkey = <l_orderkey>
  AND l_linenumber = <l_linenumber>
OPTION (FOR TIMESTAMP AS OF '<before_timestamp_utc>');
```

To measure Delta/OneLake storage impact, run the Fabric Spark notebook template in `notebooks/fabric-delta-storage-inspection.py` before and after the bulk update. Capture data-file bytes, `_delta_log` bytes, Delta history, and table row counts.

## 10. Summarize results

```bash
python3 scripts/analysis/summarize-results.py \
  --cdc results/cdc-latency.csv \
  --output results/summary.json
```

## 11. Cleanup

Stop/delete Fabric mirroring first, then verify/drop orphaned replication slots in PostgreSQL. Only then delete Azure resources:

```bash
scripts/provision/teardown-azure.sh
```

## 12. Blog post

Before writing the blog, confirm the **Deploy to Azure** button has been tested from the published repo and the Azure deployment succeeds. Write the blog only after both the agent and user have tested every repo step successfully with live Azure and Fabric resources.

Include this short activity split in the blog:

| AI agent activity | Human activity |
|---|---|
| Deploy Azure infrastructure, configure PostgreSQL prerequisites, run HammerDB load, collect metrics, summarize results | Complete Fabric portal connection/mirroring permission prompts, review results, approve final blog |

## 13. TPROC-C follow-up

Use `docs/tproc-c-plan.md` for the next write-heavy benchmark design. The recommended model is to run HammerDB TPROC-C for realistic transactional pressure while keeping marker-table batches as the precise latency probe.

Prepared scripts:

```bash
export TPROC_C_DATABASE=tprocc
export TPROC_C_USER=tprocc
export TPROC_C_PASSWORD="<benchmark-user-password>"

"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-build-tprocc.tcl
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-check-tprocc.tcl
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-run-tprocc.tcl
```

Run TPROC-C in a separate PostgreSQL database, then configure Fabric mirroring for that database before collecting CDC results under load.
