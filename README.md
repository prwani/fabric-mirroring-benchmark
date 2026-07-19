# Fabric Mirroring Benchmark

Benchmark harness for measuring Microsoft Fabric Mirroring initial-snapshot time and change-data-capture (CDC) visibility across **supported operational data sources**.

The validated default source is **Azure Database for PostgreSQL Flexible Server**. The repo is being structured as a reusable framework: common Fabric capacity/workspace setup, HammerDB VM provisioning, measurement scripts, and result summarization are shared, while source-specific prerequisites live under `sources/<source>/`.

The default experiment deploys to **Sweden Central** and uses **HammerDB TPROC-C** for both initial mirror-sync data and transactional change replication pressure. Region, warehouse count, source type, database SKU, Fabric capacity SKU, and workload settings are configurable.

## Deploy to Azure

Azure SQL Database benchmark with public network access:

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fprwani%2Ffabric-mirroring-benchmark%2Fmain%2Fazuredeploy-azure-sql-db.json)

Azure SQL Database benchmark with private network access:

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fprwani%2Ffabric-mirroring-benchmark%2Fmain%2Fazuredeploy-azure-sql-db-private.json)

PostgreSQL/default all-source template:

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fprwani%2Ffabric-mirroring-benchmark%2Fmain%2Fazuredeploy.json)

Use the **public network** Azure SQL template for the simplest baseline: it enables the Azure SQL public endpoint and creates only the necessary firewall rules. Use the **private network** template if public endpoints are prohibited: it disables the public endpoint and provisions a private endpoint, private DNS zone, and a dedicated subnet delegated for a Fabric VNet data gateway. After deployment, create the VNet data gateway in **Manage connections and gateways** in Fabric/Power BI and select the deployed gateway subnet; this Fabric resource cannot currently be created by ARM/Bicep. The all-source template keeps the older `sourceType` switch for advanced CLI scenarios, but Azure Portal custom deployment displays all top-level parameters even when conditional modules skip unrelated source resources.

Both templates deploy Azure infrastructure, then continue with the same post-deployment scripts in `docs/runbook.md`. For the public Azure SQL path, `scripts/provision/setup-fabric-items.py` creates or reuses the Fabric workspace, connection, mirrored database, and **SQL analytics endpoint** through the public API; no manual portal mirror creation is required. The private path still requires manually creating the Fabric-managed VNet data gateway before running the same script.

The public-network Azure SQL template accepts `customTags` and lets you select whether to apply them to Azure SQL, the benchmark VM, Fabric capacity, networking, and monitoring. Built-in benchmark tags remain on every resource. This supports subscriptions that require a specific tag on Azure SQL resources. The portal also requires `adminSshPublicKey` for VM access and `currentClientIpAddress` to restrict SSH access to your current machine. Generate an SSH public key using the [Azure Linux VM SSH key guidance](https://learn.microsoft.com/en-us/azure/virtual-machines/ssh-keys-portal), and enter your public IPv4 address with `/32`, for example `203.0.113.10/32`. Find it with `curl -4 ifconfig.me` or [WhatIsMyIPAddress.com](https://whatismyipaddress.com/). Azure SQL Entra admin and Fabric capacity admin default to the signed-in deploying user, but you can override them for a group or another admin account. The private-network template also requires `Microsoft.PowerPlatform` to be registered in the subscription before creating the VNet data gateway.

## What this repo provisions

- Shared Linux benchmark VM for HammerDB and measurement scripts.
- Microsoft Fabric capacity through ARM/Bicep.
- Shared networking, firewall rules, public IP, and Log Analytics.
- Source-specific database infrastructure selected by `sourceType`.
- Scripts for Fabric workspace/mirroring setup, source prerequisite validation, HammerDB data load, initial sync measurement, CDC latency measurement, and results summarization.
- SQL analytics endpoint polling uses `sqlcmd` because Fabric Warehouse / SQL analytics endpoints are SQL Server-compatible.

Fabric workspace and mirrored database items are created through Fabric REST APIs. Configure the required tenant permissions before deployment rather than substituting a manual portal mirror for the documented public path.

Mirrored database operations use the Fabric Mirroring REST API:

- <https://learn.microsoft.com/fabric/mirroring/mirrored-database-rest-api>

## Supported Fabric mirroring source list

This list tracks the Microsoft Fabric mirroring source types from the Fabric overview docs and this repo's benchmark implementation status.

| Fabric source | Mirroring type | Repo status |
|---|---|---|
| Azure Cosmos DB | Database mirroring | Roadmap |
| Azure Databricks | Metadata mirroring | Roadmap |
| Azure Database for PostgreSQL | Database mirroring | Implemented and live deployment validated |
| Azure Database for MySQL | Database mirroring, preview | Infra adapter implemented; mirroring validation pending |
| Azure SQL Database | Database mirroring | TPROC-C deployment, HammerDB MSI path, Fabric mirroring, SQL analytics endpoint validation, and post-mirroring tests live-validated |
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
| `sources/postgresql/` | Yes | TPROC-C scripts available | Default path live deployment validated | Uses PostgreSQL Flexible Server, logical WAL, transactional TPROC-C tables, and marker table. |
| `sources/mysql/` | Yes | HammerDB-compatible source docs | Pending | MySQL mirroring is preview/tenant-gated; validate availability before benchmarking. |
| `sources/azure-sql-db/` | Yes | SQL Server TPROC-C scripts available | Live deployment validated | Uses vCore Azure SQL Database, Entra-only by default, VM managed identity for HammerDB, and public-API mirror/SQL analytics endpoint provisioning. |
| `sources/sql-mi/` | Scaffold | HammerDB-compatible source docs | Pending | High-cost/long-running deployment; use only for deliberate tests. |
| `sources/sql-server/` | Scaffold | HammerDB-compatible source docs | Pending | SQL Server mirroring usually requires gateway + CDC/Agent unless using newer supported paths. |

## Defaults

| Setting | Default | Why |
|---|---:|---|
| Source type | `postgresql` | Validated default and Deploy to Azure button baseline. |
| Azure region | `swedencentral` | User-requested default; configurable for other regions. |
| TPROC-C warehouses | `10` | Transactional OLTP-shaped source with meaningful initial data and sustained writes. |
| PostgreSQL tier/SKU | `GeneralPurpose` / `Standard_D2ds_v5` | Fabric mirroring does not support Burstable tier. |
| PostgreSQL version | `16` | PostgreSQL 14+ is required for Fabric mirroring. |
| PostgreSQL auth | PostgreSQL password auth + Microsoft Entra auth | Fabric mirroring setup can use either supported authentication flow. |
| Fabric capacity SKU | `F8` | Low-cost benchmark default; compare larger SKUs only after the baseline works. |

The PostgreSQL template enables logical replication prerequisites and allow-lists only user-installable PostgreSQL extensions (`uuid-ossp`, `pg_stat_statements`). Fabric-specific mirroring components are configured by the Fabric mirroring setup flow when supported by the tenant.

## Blog

The blog series index is in `docs/blog.md`. Source-specific posts are split by adapter so each benchmark result remains independently reusable:

- `docs/blog-postgresql-tprocc.md`
- `docs/blog-azure-sql-db-tprocc.md`
- `docs/blog-azure-sql-db-tprocc.html` for the portal-ready Azure SQL Database draft

Static validation available before live deployment:

```bash
az bicep build --file infra/main.bicep
az bicep build --file infra/main.bicep --outfile azuredeploy.json
az bicep build --file infra/azure-sql-db.bicep --outfile azuredeploy-azure-sql-db.json
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

4. Follow `docs/runbook.md` and the relevant `sources/<source>/README.md` to build TPROC-C, configure Fabric mirroring, measure the initial snapshot, measure CDC latency, and clean up.
