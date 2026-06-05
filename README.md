# Fabric PostgreSQL Mirroring Benchmark

Greenfield benchmark harness for measuring Microsoft Fabric Mirroring from Azure Database for PostgreSQL Flexible Server.

The default experiment deploys to **Sweden Central** and uses **HammerDB TPROC-H scale factor 1** for the initial data-load and initial mirror-sync measurement. Region, scale factor, PostgreSQL SKU, Fabric capacity SKU, and workload settings are configurable.

## Deploy to Azure

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fprwani%2Ffabric-postgres-mirroring-benchmark%2Fmain%2Fazuredeploy.json)

The button deploys the Azure infrastructure from `azuredeploy.json`: PostgreSQL Flexible Server, benchmark VM, Fabric capacity, networking, firewall rules, and Log Analytics. Fabric workspace/mirroring setup and benchmark execution continue from `docs/runbook.md` because Fabric mirrored database configuration depends on tenant permissions and Fabric control-plane APIs.

## What this repo provisions

- Azure Database for PostgreSQL Flexible Server, non-burstable by default.
- Linux benchmark VM for HammerDB and measurement scripts.
- Microsoft Fabric capacity through ARM/Bicep.
- Networking, firewall rules, and Log Analytics.
- Scripts for Fabric workspace/mirroring setup, PostgreSQL prerequisite validation, HammerDB data load, initial sync measurement, CDC latency measurement, and results summarization.
- Fabric SQL endpoint polling uses `sqlcmd` because Fabric Warehouse / SQL analytics endpoints are SQL Server-compatible, not PostgreSQL-compatible.

Fabric workspace and mirrored database items are created through Fabric REST APIs where tenant permissions allow it. If REST setup is unavailable in your tenant, follow the manual fallback in `docs/runbook.md`.

Mirrored database operations should use the Fabric Mirroring REST API or fabric-cli where possible:

- <https://learn.microsoft.com/fabric/mirroring/mirrored-database-rest-api>
- <https://microsoft.github.io/fabric-cli/examples/item_examples/#startstop-mirrored-databases>

## Defaults

| Setting | Default | Why |
|---|---:|---|
| Azure region | `swedencentral` | User-requested default; configurable for other regions. |
| TPROC-H scale factor | `1` | Cost- and time-friendly first run; roughly 1 GB logical TPC-H scale before indexes/overhead. |
| PostgreSQL tier/SKU | `GeneralPurpose` / `Standard_D2ds_v5` | Fabric mirroring does not support Burstable tier. |
| PostgreSQL version | `16` | PostgreSQL 14+ is required for Fabric mirroring. |
| Fabric capacity SKU | `F8` | Low-cost benchmark default; compare larger SKUs only after the baseline works. |

The template enables logical replication prerequisites and allow-lists only user-installable PostgreSQL extensions (`uuid-ossp`, `pg_stat_statements`). Fabric-specific mirroring components are configured by the Fabric mirroring setup flow when supported by the tenant.

## Test gates

The blog post is intentionally not written in this scaffold. It should be the final step after both the agent and user have run the repo end-to-end successfully in a real Azure/Fabric tenant.

Static validation available before live deployment:

```bash
az bicep build --file infra/main.bicep
az bicep build --file infra/main.bicep --outfile azuredeploy.json
bash -n scripts/provision/*.sh scripts/benchmark/*.sh scripts/lib/*.sh
python3 -m py_compile scripts/provision/setup-fabric-items.py scripts/benchmark/run-cdc-latency-test.py scripts/benchmark/measure-initial-sync.py scripts/analysis/summarize-results.py
```

## Quick start

1. Deploy Azure infrastructure with the **Deploy to Azure** button after this repo is published, or use the CLI:

   ```bash
   scripts/provision/deploy-azure.sh
   ```

2. Copy `config/benchmark.env.example` to `.env` and fill in deployment outputs plus tenant-specific values.
3. Install HammerDB and PostgreSQL tools on the VM:

   ```bash
   scripts/provision/install-hammerdb.sh
   ```

4. Follow `docs/runbook.md` for PostgreSQL setup, TPROC-H load, Fabric mirroring setup, initial sync measurement, CDC latency measurement, and cleanup.
