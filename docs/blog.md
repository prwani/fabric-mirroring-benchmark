# Benchmarking Microsoft Fabric Mirroring with Azure Database for PostgreSQL, HammerDB, and Deploy to Azure

Microsoft Fabric Mirroring provides a zero-ETL way to keep operational data available in OneLake and Fabric SQL analytics endpoints. The feature is simple to use from the portal, but for performance benchmarking you need more than a demo database: you need repeatable infrastructure, a known data generator, source-side metrics, Fabric-side status, and a controlled way to measure change replication latency.

This post walks through a reproducible benchmark harness for Fabric Mirroring. The validated baseline uses Azure Database for PostgreSQL Flexible Server, HammerDB TPROC-H scale factor 1, a Linux benchmark VM, and an F8 Fabric capacity. The repo also lays the foundation for other mirroring sources such as Azure Database for MySQL, Azure SQL Database, SQL Managed Instance, and SQL Server.

> Repository: <https://github.com/prwani/fabric-mirroring-benchmark>

## What we are building

The baseline environment provisions:

- Azure Database for PostgreSQL Flexible Server as the mirrored source.
- A Linux VM used for HammerDB, PostgreSQL tools, and benchmark scripts.
- Microsoft Fabric capacity.
- Networking, firewall rules, and Log Analytics.
- Scripts for source preparation, HammerDB data load, Fabric workspace setup, row-count validation, CDC marker latency tests, and result summarization.

The benchmark has two goals:

1. Measure the initial sync behavior after Fabric Mirroring is started.
2. Measure CDC latency by inserting controlled marker rows into PostgreSQL and polling the Fabric SQL endpoint until those rows become queryable.

## Architecture

```text
HammerDB VM
  -> Azure Database for PostgreSQL Flexible Server
      -> Microsoft Fabric Mirroring
          -> Fabric mirrored database / OneLake tables
              -> Fabric SQL endpoint queries for validation and latency measurement
```

The infrastructure is deployed with Bicep. Fabric workspace and mirrored database setup use Fabric REST APIs where available, with portal steps documented for the connection and mirroring flow because tenant settings and credential prompts can vary.

## Deploy the baseline with Deploy to Azure

The fastest way to start is the Deploy to Azure button in the repo:

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fprwani%2Ffabric-mirroring-benchmark%2Fmain%2Fazuredeploy.json)

The button deploys the default PostgreSQL baseline. The key defaults are:

| Setting | Default |
|---|---:|
| Region | `swedencentral` |
| Source type | `postgresql` |
| PostgreSQL version | 16 |
| PostgreSQL SKU | `Standard_D2ds_v5`, General Purpose |
| PostgreSQL storage | 128 GiB |
| PostgreSQL auth | Password auth + Microsoft Entra auth |
| Benchmark VM | `Standard_D4s_v5`, Ubuntu 22.04 |
| Fabric capacity | F8 |
| HammerDB workload | TPROC-H |
| TPROC-H scale factor | 1 |

For local development, use the CLI path:

```bash
SOURCE_TYPE=postgresql scripts/provision/deploy-azure.sh
```

The template is parameterized, so you can change region, source type, PostgreSQL SKU, storage size, VM settings, and Fabric capacity SKU.

## Prepare PostgreSQL for mirroring

Fabric Mirroring for PostgreSQL requires logical replication prerequisites. The repo configures the Azure-side baseline with:

- System-assigned managed identity.
- `wal_level=logical`.
- Increased replication slot and WAL sender limits.
- PostgreSQL password auth and Microsoft Entra auth enabled.
- Public network access with firewall rules for Azure services and the benchmark VM.

After deployment, apply the source SQL prerequisites before loading HammerDB data:

```bash
export PGPASSWORD="$POSTGRES_ADMIN_PASSWORD"

psql "host=$POSTGRES_HOST port=5432 dbname=$POSTGRES_DATABASE user=$POSTGRES_ADMIN_USER sslmode=require" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-postgres-mirroring-prereqs.sql
```

If server parameters were changed, restart the PostgreSQL server so `wal_level=logical` takes effect.

## Install HammerDB and load TPROC-H

Install HammerDB on the benchmark VM:

```bash
scripts/provision/install-hammerdb.sh
```

Build the TPROC-H schema and data:

```bash
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-build-tproch.tcl
```

One important learning from the validation run: HammerDB expects the target TPROC-H database to be empty. Create the CDC marker table only after the HammerDB build completes:

```bash
psql "host=$POSTGRES_HOST port=5432 dbname=$POSTGRES_DATABASE user=$POSTGRES_ADMIN_USER sslmode=require" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-cdc-marker.sql
```

## Configure Fabric Mirroring

The repo can create or locate the Fabric workspace:

```bash
export FABRIC_CAPACITY_ID="<deployment-output>"
scripts/provision/setup-fabric-items.py
```

Then create the mirrored database item from the Fabric portal:

1. Open the Fabric workspace.
2. Select **New item**.
3. Choose **Mirrored Azure Database for PostgreSQL**.
4. Create a new connection to the PostgreSQL server and database.
5. Select the TPROC-H tables and `public.fabric_cdc_latency_marker`.
6. Start mirroring.

For the validated run, the Fabric REST API was also useful for discovering the mirrored database, SQL endpoint, and table-level replication state:

```bash
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/mirroredDatabases/{mirroredDatabaseId}/getMirroringStatus

POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/mirroredDatabases/{mirroredDatabaseId}/getTablesMirroringStatus
```

## Measure initial sync

Initial sync completion should be validated in two ways:

1. Fabric mirroring status is `Running`.
2. Source and Fabric row counts match for every mirrored table.

In the validated SF=1 run, row-count parity matched across all benchmark tables:

| Table | PostgreSQL rows | Fabric rows |
|---|---:|---:|
| `region` | 5 | 5 |
| `nation` | 25 | 25 |
| `supplier` | 10,000 | 10,000 |
| `customer` | 150,000 | 150,000 |
| `part` | 200,000 | 200,000 |
| `partsupp` | 800,000 | 800,000 |
| `orders` | 1,500,000 | 1,500,000 |
| `lineitem` | 6,001,259 | 6,001,259 |
| `fabric_cdc_latency_marker` | 0 | 0 |

The Fabric table status API reported all mirrored tables in `Replicating` state. The largest table, `lineitem`, reported 6,001,259 processed rows and about 2.0 GB processed bytes.

For a formal run, capture the UTC timestamp when you click **Mirror database** and the UTC timestamp when table status and row-count parity first indicate completion. In this validation run, row-count parity was confirmed, but the exact portal click timestamp was not captured, so the initial sync duration is intentionally not claimed as a precise benchmark number.

## Measure CDC latency

CDC latency uses marker rows instead of relying only on UI status. Each marker row contains:

- A unique marker ID.
- A batch ID.
- Source send timestamp.
- Source commit timestamp.
- Payload.

The polling client queries the Fabric SQL endpoint until each marker appears, then calculates:

```text
fabric_seen_ts - source_commit_ts
```

Validated idle marker results:

| Marker | Latency |
|---:|---:|
| 1 | 262.1s |
| 2 | 139.2s |
| 3 | 329.0s |
| 4 | 349.2s |
| 5 | 344.9s |

Summary:

| Metric | Value |
|---|---:|
| Count | 5 |
| Minimum | 139.2s |
| Median | 329.0s |
| p95 | 344.9s |
| Maximum | 349.2s |

This was an idle CDC test after the initial load. For a broader benchmark, repeat the same marker test while HammerDB query workload is running and while source-side CPU, storage, IOPS, connections, and WAL metrics are being captured.

## Test schema refresh on a small mirrored table

Before using a large table such as `lineitem` for schema-change and bulk-update testing, we ran a small schema refresh test on `region`.

The test added two nullable columns to PostgreSQL `public.region` and populated all five rows:

```sql
ALTER TABLE public.region
  ADD COLUMN IF NOT EXISTS mirror_schema_refresh_test_batch text;

ALTER TABLE public.region
  ADD COLUMN IF NOT EXISTS mirror_schema_refresh_test_ts timestamptz;

UPDATE public.region
SET mirror_schema_refresh_test_batch = 'region-schema-refresh-test',
    mirror_schema_refresh_test_ts = clock_timestamp()
WHERE mirror_schema_refresh_test_batch IS NULL
   OR mirror_schema_refresh_test_ts IS NULL;
```

Observed result:

| Observation | Result |
|---|---:|
| Source rows updated | 5 |
| Initial Fabric SQL endpoint visibility | 0 of 2 new columns |
| Time until new columns appeared in Fabric SQL endpoint | ~1 minute |
| Fabric table state during test | `Replicating` |
| `region` processed rows before/after | 5 -> 10 |

This small-table test showed that Fabric can automatically surface new nullable source columns in the mirrored SQL endpoint. The behavior differed from the larger `lineitem` table, where new columns did not appear automatically during the observed window. This difference should be confirmed with the Fabric product team before making a broad statement about schema refresh behavior.

## What we learned

### 1. Use a real data generator

HammerDB TPROC-H SF=1 gave a useful first baseline with millions of rows, including a `lineitem` table with more than 6 million rows. Starting with SF=1 kept cost and iteration time manageable while still exercising initial sync and CDC behavior.

### 2. PostgreSQL mirroring prerequisites matter

PostgreSQL Flexible Server needs logical WAL settings and Fabric mirroring components. Some settings are visible immediately at the ARM level but require a server restart before `pg_settings` reflects the active runtime value.

### 3. Create the marker table after HammerDB build

HammerDB expects an empty target database for the TPROC-H build. Creating benchmark helper tables before the HammerDB build caused the build to fail. The fixed workflow is:

1. Prepare PostgreSQL extensions/settings.
2. Run HammerDB TPROC-H build.
3. Create the CDC marker table.
4. Configure Fabric Mirroring.

### 4. Fabric SQL endpoint access can be automated

The mirrored database REST response includes SQL endpoint details. In the validation run, token-based ODBC access was used to query the Fabric SQL endpoint and compare row counts.

### 5. Portal intervention is still part of the path

The Azure infrastructure deployment is automated. Fabric workspace creation can be automated. The mirrored database connection and credential flow may still require a human in the Fabric portal, depending on tenant settings and connector behavior.

### 6. Expect Fabric connection retries and transient errors

During setup, Fabric returned transient connection resolution errors, including HTTP 429. Waiting, deleting stale connections, and creating a new connection resolved the issue.

### 7. Source schema changes might require a table refresh

When nullable benchmark columns were added to PostgreSQL `lineitem`, Fabric did not automatically surface those new columns in the mirrored SQL endpoint. The table had to be removed from the Fabric mirrored table list and then added again. After re-adding it, the table status returned to `Initialized` and needed to complete a new copy before it became queryable again. A follow-up test on the much smaller `region` table did surface two new nullable columns automatically after about one minute. Treat this as observed behavior to confirm with the Fabric product team before publishing externally.

## AI agent vs human activity split

| AI agent activity | Human activity |
|---|---|
| Deploy Azure infrastructure | Approve deployment parameters |
| Configure PostgreSQL prerequisites | Complete any portal-only authentication prompts |
| Install HammerDB and load TPROC-H | Create or approve Fabric mirrored database connection |
| Query Fabric REST APIs for workspace, item, and status | Confirm Fabric tenant/workspace permissions |
| Validate row-count parity | Review results |
| Run CDC marker latency tests | Decide when to pause/delete resources |
| Summarize results and draft this blog | Approve final publication |

## Cost note

Leaving the validated baseline running continuously is not free. Based on the deployed SKUs and Azure retail prices for Sweden Central, the always-on estimate was about **$1,438/month USD**, dominated by Fabric F8 capacity.

| Component | Monthly estimate |
|---|---:|
| PostgreSQL Flexible Server | ~$154 |
| HammerDB VM, OS disk, and public IP | ~$174 |
| Fabric F8 capacity | ~$1,110 |
| **Total** | **~$1,438/month** |

For short benchmark runs, pause or delete resources when finished. Fabric capacity and VM compute are the largest avoidable costs during idle time.

## Cleanup

Stop or delete Fabric mirroring first. Then verify PostgreSQL replication slots and source objects. Finally, delete the Azure resource group or run:

```bash
scripts/provision/teardown-azure.sh
```

If you only want to pause costs temporarily, stop the PostgreSQL server, deallocate the VM, and pause the Fabric capacity.

## Next steps

This repo now has a validated PostgreSQL baseline. The next useful experiments are:

1. Repeat with larger TPROC-H scale factors.
2. Run CDC latency tests while HammerDB workload is active.
3. Compare Fabric capacity SKUs.
4. Validate the MySQL, Azure SQL Database, SQL Managed Instance, and SQL Server adapters.
5. Add charts and result summaries under `results/` for each reproducible run.
