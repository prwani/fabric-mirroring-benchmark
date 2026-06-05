# Runbook

## 1. Configure defaults

Copy `config/benchmark.env.example` to `.env`.

Important defaults:

- `AZURE_LOCATION=swedencentral`
- `TPROC_H_SCALE_FACTOR=1`
- `FABRIC_CAPACITY_SKU=F8`
- `POSTGRES_SKU_TIER=GeneralPurpose`
- `POSTGRES_SKU_NAME=Standard_D2ds_v5`

Scale factor 1 is the default initial data-load target for TPROC-H. Increase it only after the full run works at SF=1.

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

Record deployment outputs in `.env`, especially:

- `POSTGRES_HOST`
- `POSTGRES_SERVER_NAME`
- `FABRIC_CAPACITY_ID`
- benchmark VM public IP

## 3. Prepare PostgreSQL

Run the SQL prerequisites:

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

After load, rerun PostgreSQL validation. Fabric mirroring requires mirrored tables to have primary keys. If HammerDB creates any table without a primary key, fix that before starting mirroring.

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

Store raw observations under `results/`.

## 8. Measure CDC latency

Run optional source load:

```bash
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-run-tproch.tcl
```

Then run controlled marker measurement:

```bash
python3 scripts/benchmark/run-cdc-latency-test.py \
  --pg-conn "$POSTGRES_PSQL_CONN" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-marker-table "$FABRIC_MARKER_TABLE"
```

Capture PostgreSQL platform metrics during the same window:

```bash
scripts/benchmark/capture-platform-metrics.sh
```

If Fabric exposes mirroring latency/status metrics through the UI/API in your tenant, export or screenshot those values and save them with the run results.

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
