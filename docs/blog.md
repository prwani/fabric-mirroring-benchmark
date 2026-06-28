# Benchmarking Microsoft Fabric Mirroring with Azure Database for PostgreSQL, HammerDB, and Deploy to Azure

Microsoft Fabric Mirroring provides a zero-ETL way to keep operational data available in OneLake and Fabric SQL analytics endpoints. The feature is simple to use from the portal, but performance benchmarking needs more than a demo database: you need repeatable infrastructure, a known data generator, source-side metrics, Fabric-side status, and a controlled way to measure change replication latency.

This post walks through a reproducible benchmark harness for Fabric Mirroring. The validated run uses Azure Database for PostgreSQL Flexible Server, HammerDB TPROC-H scale factor 1 for the initial analytical dataset, HammerDB TPROC-C for write-heavy source pressure, a Linux benchmark VM, and an F8 Fabric capacity.

> Repository: <https://github.com/prwani/fabric-mirroring-benchmark>

## What we are building

The environment provisions:

- Azure Database for PostgreSQL Flexible Server as the mirrored source.
- A Linux VM for HammerDB, PostgreSQL tools, and benchmark scripts.
- Microsoft Fabric capacity and workspace.
- Networking, firewall rules, and Log Analytics.
- Scripts for source preparation, HammerDB data load, Fabric item discovery, row-count validation, CDC marker latency tests, and result capture.

The benchmark measures four things:

1. Initial sync behavior for a TPROC-H dataset.
2. Idle CDC latency with controlled marker rows.
3. CDC latency for marker batches.
4. CDC latency while a write-heavy HammerDB TPROC-C workload is running.

The repo also lays the foundation for other mirroring sources such as Azure Database for MySQL, Azure SQL Database, SQL Managed Instance, and SQL Server.

## Architecture

```text
HammerDB VM
  -> Azure Database for PostgreSQL Flexible Server
      -> Microsoft Fabric Mirroring
          -> Fabric mirrored database / OneLake tables
              -> Fabric SQL endpoint queries for validation and latency measurement
```

The infrastructure is deployed with Bicep. Fabric workspace creation and item discovery use Fabric REST APIs where available. The mirrored database connection and source-table selection are still documented as portal steps because tenant settings and credential prompts can vary.

## Prerequisites

Use one consolidated checklist before running either TPROC-H or TPROC-C:

| Requirement | Notes |
|---|---|
| Azure subscription | Permissions to deploy resource groups, PostgreSQL Flexible Server, VM, networking, monitoring, and Fabric capacity. |
| Microsoft Fabric tenant | Fabric enabled, capacity available, and permission to create a workspace and mirrored database items. |
| PostgreSQL mirroring support | Flexible Server must use a supported SKU tier; this run used General Purpose. |
| Benchmark VM access | SSH or Azure VM Run Command access to run HammerDB and PostgreSQL tools. |
| Fabric SQL endpoint access | The benchmark uses token-based ODBC or `sqlcmd` to validate row counts and marker visibility. |
| PostgreSQL credentials | In this validation, Fabric mirroring worked with PostgreSQL Basic authentication. Microsoft Entra auth was enabled on PostgreSQL, but the Fabric connection attempt hit a SCRAM/password-style failure and needs product-team follow-up before being documented as the primary path. |

The validated defaults are:

| Setting | Default |
|---|---:|
| Region | `swedencentral` |
| Source type | `postgresql` |
| PostgreSQL version | 16 |
| PostgreSQL SKU | `Standard_D2ds_v5`, General Purpose |
| PostgreSQL storage | 128 GiB |
| PostgreSQL auth | Password auth + Microsoft Entra auth enabled |
| Benchmark VM | `Standard_D4s_v5`, Ubuntu 22.04 |
| Fabric capacity | F8 |
| TPROC-H scale factor | 1 |
| TPROC-C warehouses | 10 |
| TPROC-C run | 8 virtual users, 2-minute ramp-up, 10-minute timed duration |

## End-to-end steps for readers

### 1. Deploy the Azure baseline

The fastest way to start is the Deploy to Azure button in the repo:

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fprwani%2Ffabric-mirroring-benchmark%2Fmain%2Fazuredeploy.json)

For local development, use the CLI path:

```bash
SOURCE_TYPE=postgresql scripts/provision/deploy-azure.sh
```

The template is parameterized, so you can change region, source type, PostgreSQL SKU, storage size, VM settings, and Fabric capacity SKU.

### 2. Prepare PostgreSQL for mirroring

Fabric Mirroring for PostgreSQL requires logical replication prerequisites. The repo configures the Azure-side baseline with:

- System-assigned managed identity.
- `wal_level=logical`.
- Increased replication slot and WAL sender limits.
- PostgreSQL password auth and Microsoft Entra auth enabled.
- Public network access with firewall rules for Azure services and the benchmark VM.

Apply the source SQL prerequisites:

```bash
export PGPASSWORD="$POSTGRES_ADMIN_PASSWORD"

psql "host=$POSTGRES_HOST port=5432 dbname=$POSTGRES_DATABASE user=$POSTGRES_ADMIN_USER sslmode=require" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-postgres-mirroring-prereqs.sql
```

If server parameters were changed, restart the PostgreSQL server so `wal_level=logical` takes effect.

### 3. Install HammerDB on the benchmark VM

```bash
scripts/provision/install-hammerdb.sh
```

The validation used HammerDB 5.0.

### 4. Build the TPROC-H database

Build the TPROC-H schema and data:

```bash
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-build-tproch.tcl
```

HammerDB expects the target TPROC-H database to be empty. Create the CDC marker table only after the HammerDB build completes:

```bash
psql "host=$POSTGRES_HOST port=5432 dbname=$POSTGRES_DATABASE user=$POSTGRES_ADMIN_USER sslmode=require" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-cdc-marker.sql
```

### 5. Configure Fabric Mirroring for TPROC-H

The repo can create or locate the Fabric workspace:

```bash
export FABRIC_CAPACITY_ID="<deployment-output>"
scripts/provision/setup-fabric-items.py
```

Then create the mirrored database item from the Fabric portal:

1. Open the Fabric workspace.
2. Select **New item**.
3. Choose **Mirrored Azure Database for PostgreSQL**.
4. Create a new connection to the PostgreSQL server and TPROC-H database.
5. Use PostgreSQL Basic authentication if your Fabric Entra-auth connection fails.
6. Select the TPROC-H tables and `public.fabric_cdc_latency_marker`.
7. Start mirroring.

Use the Fabric REST API to discover item details and table status:

```bash
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/mirroredDatabases/{mirroredDatabaseId}/getMirroringStatus

POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/mirroredDatabases/{mirroredDatabaseId}/getTablesMirroringStatus
```

### 6. Validate TPROC-H initial sync

Initial sync completion should be validated in two ways:

1. Fabric table status shows `Replicating`.
2. Source and Fabric SQL endpoint row counts match for every mirrored table.

In the validated TPROC-H SF=1 run, row-count parity matched across all benchmark tables:

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

The Fabric table status API reported all mirrored tables in `Replicating` state. The largest table, `lineitem`, reported 6,001,259 processed rows and about 2.0 GiB processed bytes.

For a formal run, capture the UTC timestamp when you click **Mirror database** and the UTC timestamp when table status and row-count parity first indicate completion. In this validation run, row-count parity was confirmed, but the exact portal click timestamp was not captured, so the initial TPROC-H sync duration is intentionally not claimed as a precise benchmark number.

### 7. Run idle CDC marker tests

CDC latency uses marker rows instead of relying only on UI status. Each marker row contains a marker ID, batch ID, source send timestamp, source commit timestamp, and payload.

The polling client queries the Fabric SQL endpoint until each marker appears, then calculates:

```text
fabric_seen_ts - source_commit_ts
```

Run the single-row or bulk marker tests from the benchmark scripts:

```bash
python3 scripts/benchmark/run-cdc-latency-test.py
python3 scripts/benchmark/run-cdc-bulk-test.py --operation insert
python3 scripts/benchmark/run-cdc-bulk-test.py --operation update
```

### 8. Build the TPROC-C database

Use a separate PostgreSQL database for TPROC-C so the TPROC-H baseline remains stable:

```bash
export TPROC_C_DATABASE=tprocc
export TPROC_C_USER=tprocc
export TPROC_C_PASSWORD="<benchmark-user-password>"
export TPROC_C_WAREHOUSES=10
export TPROC_C_BUILD_VUSERS=4

"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-build-tprocc.tcl
"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-check-tprocc.tcl
```

Create the marker table in the TPROC-C database:

```bash
psql "host=$POSTGRES_HOST port=5432 dbname=$TPROC_C_DATABASE user=$POSTGRES_ADMIN_USER sslmode=require" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-tprocc-marker.sql
```

One implementation detail: HammerDB creates or alters the configured TPROC-C benchmark role. Do not use the PostgreSQL admin as `TPROC_C_USER`; use a dedicated benchmark role.

### 9. Configure Fabric Mirroring for TPROC-C

Because TPROC-C is in a separate PostgreSQL database, create a separate Fabric mirrored database item for `tprocc`.

Select these `public` tables:

| TPROC-C table |
|---|
| `warehouse` |
| `district` |
| `customer` |
| `item` |
| `stock` |
| `orders` |
| `new_order` |
| `order_line` |
| `history` |
| `fabric_cdc_latency_marker` |

Wait until all tables are `Replicating`, then verify row counts from the Fabric SQL endpoint before starting the write workload.

In the validation run, the initial TPROC-C mirror reached row-count parity:

| Table | PostgreSQL rows | Fabric rows |
|---|---:|---:|
| `warehouse` | 10 | 10 |
| `district` | 100 | 100 |
| `item` | 100,000 | 100,000 |
| `stock` | 1,000,000 | 1,000,000 |
| `customer` | 300,000 | 300,000 |
| `orders` | 300,000 | 300,000 |
| `order_line` | 3,001,740 | 3,001,740 |
| `new_order` | 90,000 | 90,000 |
| `history` | 300,000 | 300,000 |
| `fabric_cdc_latency_marker` | 0 | 0 |

### 10. Run TPROC-C and marker probes together

Start HammerDB TPROC-C:

```bash
export TPROC_C_VUSERS=8
export TPROC_C_RAMPUP_MINUTES=2
export TPROC_C_DURATION_MINUTES=10

"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-run-tprocc.tcl
```

While HammerDB is running, insert marker batches into the TPROC-C marker table and poll the TPROC-C Fabric SQL endpoint. This separates source workload pressure from the latency measurement.

## Validated results

### TPROC-H initial sync

TPROC-H SF=1 produced more than 8.6 million rows across the mirrored tables. Row-count parity was confirmed for all mirrored tables, including `lineitem` with 6,001,259 rows.

The initial sync duration is not reported as a precise metric because the exact portal start timestamp was not captured. The row-count parity result is still useful as a correctness baseline.

### Idle single-row CDC marker latency

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

### Idle bulk marker insert/update latency

Bulk insert test:

- Operation: insert into `public.fabric_cdc_latency_marker`
- Batch size: 500 rows
- Batches: 3
- Timeout: 30 minutes

| Batch | Rows visible in Fabric | Latency from last source commit |
|---:|---:|---:|
| 1 | 500 / 500 | 207.4s |
| 2 | 500 / 500 | 162.6s |
| 3 | 500 / 500 | 161.3s |

Bulk insert summary:

| Metric | Value |
|---|---:|
| Total rows inserted | 1,500 |
| Completed batches | 3 / 3 |
| Minimum batch latency | 161.3s |
| Median batch latency | 162.6s |
| Maximum batch latency | 207.4s |

Bulk update test:

| Batch | Rows visible in Fabric | Latency from last source commit |
|---:|---:|---:|
| 1 | 500 / 500 | 159.9s |

### TPROC-C write workload and marker latency

The validated TPROC-C run used:

| Setting | Value |
|---|---:|
| Warehouses | 10 |
| Virtual users | 8 |
| Ramp-up | 2 minutes |
| Timed duration | 10 minutes |
| HammerDB result | 22,167 NOPM |
| PostgreSQL TPM | 51,134 TPM |

Marker probes were inserted into `tprocc.public.fabric_cdc_latency_marker` while the TPROC-C workload was active.

| Batch | Rows visible in Fabric | Latency from last source commit |
|---:|---:|---:|
| 1 | 500 / 500 | 192.4s |
| 2 | 500 / 500 | 311.7s |
| 3 | 500 / 500 | 331.5s |

Summary:

| Metric | Value |
|---|---:|
| Total marker rows inserted | 1,500 |
| Completed batches | 3 / 3 |
| Minimum batch latency | 192.4s |
| Median batch latency | 311.7s |
| Maximum batch latency | 331.5s |

The Fabric table status API showed the TPROC-C tables continuing in `Replicating` state after the workload. The marker table reported 1,500 processed rows. The SQL endpoint showed all three marker batches after the final poll.

### Large-table update scenario

We prepared a large-table update test on `lineitem` by adding benchmark-only nullable columns:

```sql
ALTER TABLE public.lineitem
  ADD COLUMN IF NOT EXISTS mirror_benchmark_update_ts timestamptz;

ALTER TABLE public.lineitem
  ADD COLUMN IF NOT EXISTS mirror_benchmark_update_batch text;
```

Those columns were populated for all 6,001,259 `lineitem` rows with baseline values. The PostgreSQL update completed in about 3 minutes 42 seconds.

Fabric did not automatically surface the new `lineitem` columns during the initial observed window. The table was removed from the Fabric mirrored table list and added again. After re-adding and allowing mirroring to catch up, the Fabric SQL endpoint showed both benchmark columns and all 6,001,259 baseline rows.

The intended next test is to update a subset such as 100K or 1M `lineitem` rows and measure source update duration, Fabric visibility latency, processed rows/bytes, and Delta/OneLake data-file growth.

### Small-table schema refresh and time-travel observations

Before relying on large-table schema behavior, we ran a small schema refresh test on `region`.

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

After the `region` schema refresh test, Fabric SQL endpoint time-travel syntax returned:

```text
The object isn't versioned, so time travel isn't supported.
```

This suggests that the Fabric Warehouse time-travel syntax documented for Warehouse objects might not apply directly to the mirrored SQL endpoint object used in this run. For the storage/time-travel part of the benchmark, the safer next step is to use the Spark/Delta notebook path against the mirrored OneLake table and confirm SQL endpoint time-travel support with the Fabric product team before publishing external claims.

## What we learned

### 1. Use a real data generator

HammerDB TPROC-H SF=1 gave a useful initial-sync baseline with millions of rows. HammerDB TPROC-C added sustained write pressure so marker latency could be measured while source tables were actively changing.

### 2. Keep analytical and write-heavy workloads separate

Using separate PostgreSQL databases for TPROC-H and TPROC-C kept the TPROC-H baseline stable and made it easier to configure a separate Fabric mirrored database for write-heavy testing.

### 3. PostgreSQL mirroring prerequisites matter

PostgreSQL Flexible Server needs logical WAL settings and Fabric mirroring components. Some settings are visible immediately at the ARM level but require a server restart before `pg_settings` reflects the active runtime value.

### 4. Create helper objects after HammerDB builds

HammerDB TPROC-H expects an empty target database. For TPROC-C, HammerDB creates or alters the benchmark role and database. The reliable workflow is:

1. Prepare PostgreSQL extensions/settings.
2. Run the HammerDB schema build.
3. Create benchmark helper tables.
4. Configure Fabric Mirroring.

### 5. Fabric SQL endpoint access can be automated

The mirrored database REST response includes SQL endpoint details. In the validation run, token-based ODBC access was used to query the Fabric SQL endpoint and compare row counts.

### 6. Portal intervention is still part of the path

The Azure infrastructure deployment is automated. Fabric workspace creation can be automated. The mirrored database connection and credential flow may still require a human in the Fabric portal, depending on tenant settings and connector behavior.

### 7. Expect Fabric connection retries and transient errors

During setup, Fabric returned transient connection resolution errors, including HTTP 429. Waiting, deleting stale connections, and creating a new connection resolved the issue.

### 8. Source schema changes need more product-team validation

The small `region` table surfaced new nullable columns automatically after about one minute. The large `lineitem` table did not surface new columns during the observed window and needed to be removed and re-added. Treat this as an observation to validate with the Fabric product team before publishing a broad schema-refresh claim.

## AI agent vs human activity split

| AI agent activity | Human activity |
|---|---|
| Deploy Azure infrastructure | Approve deployment parameters |
| Configure PostgreSQL prerequisites | Complete any portal-only authentication prompts |
| Install HammerDB and load TPROC-H/TPROC-C | Create or approve Fabric mirrored database connections |
| Query Fabric REST APIs for workspace, item, and status | Confirm Fabric tenant/workspace permissions |
| Validate row-count parity | Select mirrored source tables in the Fabric portal |
| Run CDC marker latency tests | Enable JIT/SSH access when needed |
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

This repo now has a validated PostgreSQL baseline with both TPROC-H initial sync and TPROC-C write-load CDC measurements. The next useful experiments are:

1. Repeat with larger TPROC-H scale factors.
2. Run the prepared large `lineitem` update scenario and inspect OneLake/Delta storage growth.
3. Compare Fabric capacity SKUs.
4. Validate the MySQL, Azure SQL Database, SQL Managed Instance, and SQL Server adapters.
5. Add charts and result summaries under `results/` for each reproducible run.
