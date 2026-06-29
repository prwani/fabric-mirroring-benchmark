# Benchmarking Microsoft Fabric Mirroring with HammerDB TPROC-C

Microsoft Fabric Mirroring is designed for operational data sources, so the benchmark should look like an operational workload. For this experiment I used HammerDB **TPROC-C** instead of analytical TPROC-H/TPC-H data. TPROC-C gives a realistic OLTP-shaped schema, a large initial dataset, and transactional changes that can be used to measure mirroring freshness.

The goal was to answer four practical questions:

1. How long does initial mirroring take for a 10-warehouse TPROC-C source?
2. How quickly do committed source changes appear in the Fabric SQL endpoint?
3. What happens when a new table is added after mirroring starts and the mirror is configured to auto-add new tables?
4. How does mirroring handle a larger transactional update on a million-row OLTP table?

## Architecture

The benchmark uses this flow:

```text
HammerDB VM
   |
   | TPROC-C schema build and workload
   v
Azure operational source database
   |
   | Microsoft Fabric Mirroring
   v
Fabric mirrored database / SQL endpoint
   |
   | Row-count and latency queries
   v
Benchmark result files
```

The same repository supports Azure Database for PostgreSQL Flexible Server and Azure SQL Database. The shared infrastructure provisions the benchmark VM, Fabric capacity, workspace, networking, and monitoring. Source-specific adapters provision and configure the database engine.

## Prerequisites

Use one consolidated setup regardless of the source engine:

| Requirement | Notes |
|---|---|
| Azure subscription | Contributor access to create a resource group, database source, VM, Fabric capacity, and monitoring resources. |
| Microsoft Fabric tenant | Fabric capacity enabled and permission to create workspace items. |
| Azure CLI | Used for infrastructure deployment and token-based test automation. |
| Fabric portal access | Used to complete mirrored database connection prompts when interactive authentication is required. |
| HammerDB 5.0 | Installed on the benchmark VM by `scripts/provision/install-hammerdb.sh`. |
| Source database | Azure Database for PostgreSQL Flexible Server or Azure SQL Database. |
| Authentication | PostgreSQL uses database credentials/Entra where configured. Azure SQL in this run used Entra-only authentication and the VM managed identity for HammerDB. |

Default benchmark settings:

| Setting | Value |
|---|---|
| Region | `swedencentral` |
| Workload | HammerDB TPROC-C |
| Scale | 10 warehouses |
| Build virtual users | 4 |
| Timed workload virtual users | 8 |
| Timed workload duration | 10 minutes after 2-minute ramp-up |
| Fabric capacity | F8 for the baseline run |

## Step-by-step benchmark flow

1. Clone the repo and copy `config/benchmark.env.example` to `.env`.
2. Set the source type, region, admin identities, and operator IP.
3. Deploy Azure infrastructure with `scripts/provision/deploy-azure.sh` or the generated ARM template.
4. SSH to the benchmark VM and run `scripts/provision/install-hammerdb.sh`.
5. Build HammerDB TPROC-C data:
   - PostgreSQL: `scripts/benchmark/hammerdb-build-tprocc.tcl`
   - Azure SQL Database: `scripts/benchmark/hammerdb-build-sqlserver-tprocc.tcl`
6. Add benchmark-owned columns to `stock` before mirroring starts:
   - `mirror_benchmark_update_batch`
   - `mirror_benchmark_update_ts`
   - `mirror_benchmark_payload`
7. Create `fabric_cdc_latency_marker` after the HammerDB build.
8. Configure Fabric Mirroring and select all TPROC-C tables plus the marker table.
9. Measure initial sync by comparing source and Fabric row counts.
10. Run post-mirroring tests:
    - Marker insert latency.
    - New-table auto-replication.
    - Small-table schema evolution on `warehouse`.
    - 100K-row update on `stock`.
11. Save raw JSON/CSV results under `results/` and summarize.

## Tables mirrored

The mirror includes all TPROC-C tables and one benchmark marker table:

| Table | Purpose |
|---|---|
| `warehouse` | Small table; used for schema-evolution test. |
| `district` | TPROC-C reference/transactional table. |
| `item` | Item master table. |
| `stock` | Large 1,000,000-row table; used for bulk update test. |
| `customer` | Customer table. |
| `orders` | Order header table. |
| `order_line` | Largest transactional detail table. |
| `new_order` | New-order transaction table. |
| `history` | Payment history table. |
| `fabric_cdc_latency_marker` | Controlled CDC latency marker table. |

## PostgreSQL validation result

The PostgreSQL TPROC-C path was validated first with 10 warehouses and Fabric mirroring enabled on the `tprocc` database.

| Table | Fabric rows |
|---|---:|
| `warehouse` | 10 |
| `district` | 100 |
| `item` | 100,000 |
| `stock` | 1,000,000 |
| `customer` | 300,000 |
| `orders` | 300,000 |
| `order_line` | 3,001,740 |
| `new_order` | 90,000 |
| `history` | 300,000 |
| `fabric_cdc_latency_marker` | 0 before CDC tests |

HammerDB timed workload result:

| Metric | Value |
|---|---:|
| NOPM | 22,167 |
| PostgreSQL TPM | 51,134 |

Marker latency under HammerDB load used three 500-row batches. The measured last-commit latencies were:

| Batch | Last-commit latency |
|---|---:|
| 1 | 192.4 seconds |
| 2 | 311.7 seconds |
| 3 | 331.5 seconds |

## Azure SQL Database validation result

The Azure SQL Database path used a fresh source database `tprocc` on `sql-fsqlmb-53vwnrvnudnko.database.windows.net`. The tenant enforced Entra-only authentication, so HammerDB connected from the benchmark VM with the VM system-assigned managed identity. SQL Server BCP loading was disabled for this path because HammerDB's BCP code path attempted SQL authentication; the ODBC/MSI path was used instead.

Source setup:

| Setting | Value |
|---|---|
| Database | `tprocc` |
| SKU during final build | `GP_Gen5_4` |
| HammerDB warehouses | 10 |
| Build virtual users | 4 |
| Fabric workspace | `fsqlmb-benchmark` |
| Mirrored database item | `tprocc` |
| SQL endpoint | `pindfi4msvfe7lkp6tm4de6jo4-pdoctk7rph7urpg5px4zdecfoi.datawarehouse.fabric.microsoft.com` |
| Mirroring option | Add any new tables to replication enabled |

Initial row-count parity succeeded:

| Table | Source rows | Fabric rows |
|---|---:|---:|
| `dbo.warehouse` | 10 | 10 |
| `dbo.district` | 100 | 100 |
| `dbo.item` | 100,000 | 100,000 |
| `dbo.stock` | 1,000,000 | 1,000,000 |
| `dbo.customer` | 300,000 | 300,000 |
| `dbo.orders` | 300,000 | 300,000 |
| `dbo.order_line` | 3,000,481 | 3,000,481 |
| `dbo.new_order` | 90,000 | 90,000 |
| `dbo.history` | 300,000 | 300,000 |

Post-mirroring test results:

| Scenario | Result |
|---|---:|
| Marker insert visibility | 354.6 seconds |
| New table auto-replication, 1,000 rows | 151.9 seconds |
| `warehouse` schema evolution and 2 updated rows | 430.2 seconds |
| `stock` 100K-row update visibility | 174.2 seconds |

The new-table scenario verified that Fabric picked up a newly created table because **add any new tables to replication** was enabled. The table `dbo.fabric_auto_table_125329_c687` reached 1,000/1,000 rows in Fabric.

The large-update scenario used `stock`, not an analytical table. This keeps the benchmark aligned with OLTP mirroring. The test updated 100,000 rows by setting `mirror_benchmark_update_batch`, `mirror_benchmark_update_ts`, and `mirror_benchmark_payload`; Fabric showed all 100,000 updated rows after about 174 seconds from the source update timestamp.

## Notes and lessons learned

- TPROC-C is a better fit than TPROC-H for mirroring benchmarks because the source represents a transactional system.
- Add benchmark-only `stock` columns before mirroring starts. That makes large-update measurements part of the initial mirrored schema and avoids mixing the bulk-update test with schema evolution.
- Test post-mirroring schema evolution on a small table such as `warehouse`.
- For Azure SQL Entra-only tenants, grant the Fabric Organizational account as a contained database user with:
  - `SELECT`
  - `ALTER ANY EXTERNAL MIRROR`
  - `VIEW DATABASE PERFORMANCE STATE`
  - `VIEW DATABASE SECURITY STATE`
- If Azure SQL cannot resolve Entra principals because the SQL server identity lacks Directory Readers, create the contained user by object ID. The repo includes `scripts/provision/grant-azure-sql-fabric-entra-principal-msi.py` for this.
- Fabric mirroring status APIs and the Fabric SQL endpoint can differ briefly. For latency tests, reconnect or refresh SQL endpoint sessions between polls.
- Scaling Azure SQL during an active HammerDB build can interrupt ODBC sessions. Scale before starting the build when possible.

## Cleanup

Delete Fabric mirrored items first, then remove Azure resources. For Azure SQL, delete obsolete non-TPROC-C databases before cleanup if you pivoted workloads during testing.

```bash
scripts/provision/teardown-azure.sh
```

## Reproduce this benchmark

The full workflow is captured in `docs/runbook.md`. Start with the default 10-warehouse scale, validate end-to-end behavior, then increase warehouses, Fabric capacity, or source database compute to explore throughput and latency tradeoffs.
