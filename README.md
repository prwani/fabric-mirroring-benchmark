# Fabric Mirroring Benchmark

Benchmark harness for measuring Microsoft Fabric Mirroring initial sync time and change replication latency across supported source systems.

The validated default source is **Azure Database for PostgreSQL Flexible Server**. The repo is being structured as a reusable framework: common Fabric capacity/workspace setup, HammerDB VM provisioning, measurement scripts, and result summarization are shared, while source-specific prerequisites live under `sources/<source>/`.

The default experiment deploys to **Sweden Central** and uses **HammerDB TPROC-H scale factor 1** for the initial data-load and initial mirror-sync measurement. Region, scale factor, source type, database SKU, Fabric capacity SKU, and workload settings are configurable.

## Deploy to Azure

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fprwani%2Ffabric-mirroring-benchmark%2Fmain%2Fazuredeploy.json)

The button deploys the default Azure infrastructure from `azuredeploy.json`: PostgreSQL Flexible Server, benchmark VM, Fabric capacity, networking, firewall rules, and Log Analytics. Fabric workspace/mirroring setup and benchmark execution continue from `docs/runbook.md` because Fabric mirrored database configuration depends on tenant permissions and Fabric control-plane APIs.

For non-default sources, use the CLI path with `SOURCE_TYPE` until each source is live-validated.

## What this repo provisions

- Shared Linux benchmark VM for HammerDB and measurement scripts.
- Microsoft Fabric capacity through ARM/Bicep.
- Shared networking, firewall rules, public IP, and Log Analytics.
- Source-specific database infrastructure selected by `sourceType`.
- Scripts for Fabric workspace/mirroring setup, source prerequisite validation, HammerDB data load, initial sync measurement, CDC latency measurement, and results summarization.
- Fabric SQL endpoint polling uses `sqlcmd` because Fabric Warehouse / SQL analytics endpoints are SQL Server-compatible.

Fabric workspace and mirrored database items are created through Fabric REST APIs where tenant permissions allow it. If REST setup is unavailable in your tenant, follow the manual fallback in `docs/runbook.md`.

Mirrored database operations should use the Fabric Mirroring REST API or fabric-cli where possible:

- <https://learn.microsoft.com/fabric/mirroring/mirrored-database-rest-api>
- <https://microsoft.github.io/fabric-cli/examples/item_examples/#startstop-mirrored-databases>

## Supported Fabric mirroring source list

This list tracks the Microsoft Fabric mirroring source types from the Fabric overview docs and this repo's benchmark implementation status.

| Fabric source | Mirroring type | Repo status |
|---|---|---|
| Azure Cosmos DB | Database mirroring | Roadmap |
| Azure Databricks | Metadata mirroring | Roadmap |
| Azure Database for PostgreSQL | Database mirroring | Implemented and live deployment validated |
| Azure Database for MySQL | Database mirroring, preview | Infra adapter implemented; mirroring validation pending |
| Azure SQL Database | Database mirroring | Infra adapter implemented; HammerDB/Entra-only validation pending |
| Azure SQL Managed Instance | Database mirroring | Experimental high-cost adapter scaffold; validation pending |
| Dremio | Metadata mirroring, preview | Roadmap |
| Google BigQuery | Database mirroring, preview | Roadmap |
| Oracle | Database mirroring | Roadmap |
| SAP | Database mirroring | Roadmap |
| Snowflake | Database mirroring | Roadmap |
| SQL Server | Database mirroring | Experimental Azure VM scaffold; gateway/CDC validation pending |
| Open mirrored databases | Open mirroring | Roadmap |
| Fabric SQL database | Database mirroring | Roadmap |

## Implemented source adapters

| Source adapter | Infra | HammerDB assets | Fabric mirroring validation | Notes |
|---|---|---|---|---|
| `sources/postgresql/` | Yes | TPROC-H scripts available | Default path live deployment validated | Uses PostgreSQL Flexible Server, logical WAL, and marker table. |
| `sources/mysql/` | Yes | HammerDB-compatible source docs | Pending | MySQL mirroring is preview/tenant-gated; validate availability before benchmarking. |
| `sources/azure-sql-db/` | Yes | HammerDB-compatible source docs | Pending | Uses Entra-only Azure SQL server and vCore database. HammerDB auth path needs validation. |
| `sources/sql-mi/` | Scaffold | HammerDB-compatible source docs | Pending | High-cost/long-running deployment; use only for deliberate tests. |
| `sources/sql-server/` | Scaffold | HammerDB-compatible source docs | Pending | SQL Server mirroring usually requires gateway + CDC/Agent unless using newer supported paths. |

## Defaults

| Setting | Default | Why |
|---|---:|---|
| Source type | `postgresql` | Validated default and Deploy to Azure button baseline. |
| Azure region | `swedencentral` | User-requested default; configurable for other regions. |
| TPROC-H scale factor | `1` | Cost- and time-friendly first run; roughly 1 GB logical TPC-H scale before indexes/overhead. |
| PostgreSQL tier/SKU | `GeneralPurpose` / `Standard_D2ds_v5` | Fabric mirroring does not support Burstable tier. |
| PostgreSQL version | `16` | PostgreSQL 14+ is required for Fabric mirroring. |
| PostgreSQL auth | PostgreSQL password auth + Microsoft Entra auth | Fabric mirroring setup can use either supported authentication flow. |
| Fabric capacity SKU | `F8` | Low-cost benchmark default; compare larger SKUs only after the baseline works. |

The PostgreSQL template enables logical replication prerequisites and allow-lists only user-installable PostgreSQL extensions (`uuid-ossp`, `pg_stat_statements`). Fabric-specific mirroring components are configured by the Fabric mirroring setup flow when supported by the tenant.

## Blog

The first end-to-end PostgreSQL baseline write-up is available in `docs/blog.md`.

Static validation available before live deployment:

```bash
az bicep build --file infra/main.bicep
az bicep build --file infra/main.bicep --outfile azuredeploy.json
bash -n scripts/provision/*.sh scripts/benchmark/*.sh scripts/lib/*.sh
python3 -m py_compile scripts/provision/setup-fabric-items.py scripts/benchmark/run-cdc-latency-test.py scripts/benchmark/measure-initial-sync.py scripts/analysis/summarize-results.py
```

## Quick start

1. Deploy Azure infrastructure with the **Deploy to Azure** button for the validated PostgreSQL baseline, or use the CLI:

   ```bash
   SOURCE_TYPE=postgresql scripts/provision/deploy-azure.sh
   ```

2. Copy `config/benchmark.env.example` to `.env` and fill in deployment outputs plus tenant-specific values.
3. Install HammerDB and source client tools on the benchmark VM:

   ```bash
   scripts/provision/install-hammerdb.sh
   ```

4. Follow `docs/runbook.md` and the relevant `sources/<source>/README.md` for source-specific setup, Fabric mirroring setup, initial sync measurement, CDC latency measurement, and cleanup.
