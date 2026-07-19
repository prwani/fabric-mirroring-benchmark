# Benchmarking Microsoft Fabric Mirroring with Azure SQL Database and HammerDB TPROC-C

This post is part of a benchmark series for Microsoft Fabric Mirroring across **supported operational data sources**. This article focuses on **Azure SQL Database** as the source system and **HammerDB TPROC-C** as the transactional workload.

The goal is not to publish a universal service-level number. The goal is to provide a reproducible way to deploy a source system, generate an OLTP dataset, configure Fabric Mirroring, and measure how quickly data becomes queryable through the Fabric **SQL analytics endpoint** for specific test scenarios.

## What is Microsoft Fabric Mirroring?

Microsoft Fabric Mirroring continuously replicates supported operational data sources into Fabric so the data can be queried and analyzed without building a custom ETL pipeline. For this benchmark, Azure SQL Database is mirrored into a Fabric mirrored database. Validation queries run against its SQL analytics endpoint.

The benchmark uses HammerDB **TPROC-C** because Fabric Mirroring sources are usually transactional systems. TPROC-C gives us:

- An initial OLTP-shaped dataset.
- Ongoing inserts, updates, and deletes from a transactional workload.
- A large `stock` table that can be used for controlled bulk-update tests.

Architecture:

![HammerDB to Azure SQL Database to Microsoft Fabric Mirroring benchmark flow](media/azure-sql-fabric-mirroring-flow.svg)

```text
HammerDB VM
  -> Azure SQL Database
      -> Microsoft Fabric Mirroring
          -> Fabric mirrored database SQL analytics endpoint
              -> Row-count and CDC visibility checks
```

## Prerequisites

| Requirement | Notes |
|---|---|
| Azure subscription | Permission to deploy a resource group, Azure SQL Database, VM, Fabric capacity, networking, firewall rules, and monitoring resources. |
| Microsoft Fabric tenant | Permission to create a workspace, assign Fabric capacity, and create mirrored database items. |
| Fabric account | An account that can create the mirrored database connection. Use **Organizational account** authentication for the Entra-only configuration in this guide. |
| Azure SQL Entra admin principal | UPN and object ID for the principal that will be configured as the Azure SQL Microsoft Entra administrator. |
| Admin SSH public key | Required by the Deploy to Azure form for the benchmark VM. Generate an SSH key pair and paste the public key value, for example the contents of `~/.ssh/id_rsa.pub` or `~/.ssh/id_ed25519.pub`. See [Create and use an SSH public-private key pair for Linux VMs in Azure](https://learn.microsoft.com/en-us/azure/virtual-machines/ssh-keys-portal). |
| Current client IP address | Required by the Deploy to Azure form to restrict SSH access to your current machine. Use your public IPv4 address in CIDR form, for example `203.0.113.10/32`. From a terminal, `curl -4 ifconfig.me` can show the IP; append `/32` for a single-address rule. You can also use [WhatIsMyIPAddress.com](https://whatismyipaddress.com/). |

## Default benchmark setup

| Setting | Value |
|---|---|
| Source system | Azure SQL Database |
| Database name | `tprocc` |
| Azure SQL default SKU | `GP_Gen5_4` |
| Fabric capacity SKU | `F8` |
| Workload | HammerDB TPROC-C |
| TPROC-C scale | 10 warehouses |
| Build virtual users | 4 |
| Mirroring option for new-table scenario | Add any new tables to replication enabled |

## Deployment instructions

### 1. Deploy Azure resources

The easiest deployment path is the public-network Azure SQL-specific **Deploy to Azure** button. It uses `azuredeploy-azure-sql-db.json`, so the Azure Portal form only asks for Azure SQL Database, benchmark VM, Fabric capacity, and shared deployment values:

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fprwani%2Ffabric-mirroring-benchmark%2Fmain%2Fazuredeploy-azure-sql-db.json)

Set these important parameters:

| Parameter | Value |
|---|---|
| `location` | `swedencentral`, or another region where Azure SQL Database, VM, and Fabric capacity are available |
| `adminSshPublicKey` | Your SSH public key, such as the contents of `~/.ssh/id_ed25519.pub` |
| `currentClientIpAddress` | Your public IPv4 address with `/32`, such as `203.0.113.10/32`; find it with `curl -4 ifconfig.me` or [WhatIsMyIPAddress.com](https://whatismyipaddress.com/) |
| `azureSqlDatabaseName` | `tprocc` |
| `azureSqlAzureAdOnlyAuthentication` | `true` for Entra-only tenants |
| `sqlEntraAdminLogin` / `sqlEntraAdminObjectId` | Defaults to the signed-in deploying user; override if another user or group should administer Azure SQL |
| `fabricAdminUpn` | Defaults to the signed-in deploying user; override if another user should administer the Fabric capacity |
| `customTags` | Optional JSON tags, for example `{"CostCenter":"12345"}`; built-in benchmark tags are retained |
| `applyCustomTagsToAzureSql` | Keep `true` to apply `customTags` to the Azure SQL server and database; use the equivalent selectors to choose VM, Fabric, networking, and monitoring |
| `fabricCapacitySku` | `F8` for the baseline run |

The template deploys Azure infrastructure and the benchmark VM is provisioned with a system-assigned managed identity. Both the **Deploy to Azure** template and the CLI deployment use the same repository post-deployment script workflow to provision the source connection, mirrored database, and SQL analytics endpoint. The public path does not require manually creating a mirror in the Fabric portal.

For an Azure SQL environment that prohibits public endpoints, use the [private-network template](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fprwani%2Ffabric-mirroring-benchmark%2Fmain%2Fazuredeploy-azure-sql-db-private.json). It disables Azure SQL public network access and deploys a private endpoint, private DNS zone, and dedicated VNet data gateway subnet. Register `Microsoft.PowerPlatform`, then create the VNet data gateway manually in **Manage connections and gateways** and select it when configuring the Fabric connection.

HammerDB, `sqlcmd`, and the SQL Server ODBC driver are runtime tools used on the benchmark VM after deployment. They are not prerequisites for the reader's local machine.

Use the post-deployment scripts below for the public path. The only interactive exception in this guide is creating a VNet data gateway for the private-network option; it is a Fabric-managed gateway resource, not manual mirror creation.

The repository still keeps the original all-source `azuredeploy.json` for advanced use, but Azure Portal custom deployment does not hide unrelated parameters in a single conditional ARM template. Use the source-specific template for a cleaner portal experience.

If you prefer a terminal-driven setup, or you are using an AI agent to run the deployment, use the CLI script path:

```bash
SOURCE_TYPE=azure-sql-db \
AZURE_RESOURCE_GROUP=rg-fabric-sqldb-mirror-bench \
PROJECT_NAME=fsqlmb \
scripts/provision/deploy-azure.sh
```

### 2. Optionally provision a Fabric source app and Directory Readers

The script-based deployment can create the source service principal and grant the Azure SQL logical-server managed identity **Directory Readers**. Set both flags before deployment when creating a new service-principal connection:

```bash
export ASSIGN_AZURE_SQL_SERVER_DIRECTORY_READERS=true
export PROVISION_FABRIC_SOURCE_APP=true
SOURCE_TYPE=azure-sql-db scripts/provision/deploy-azure.sh
```

`ASSIGN_AZURE_SQL_SERVER_DIRECTORY_READERS` requires a tenant administrator who can assign directory roles. Directory Readers lets the Azure SQL server managed identity resolve the source service principal while `grant-azure-sql-master-entra-principal-msi.py` creates its server login. The generated `results/fabric-source-app.env` contains a client secret, is ignored by Git through `*.env`, and is written with mode `0600`. Source it only in the protected benchmark session:

```bash
source results/fabric-source-app.env
```

For an existing approved connection, set `FABRIC_CONNECTION_ID` instead; do not create another app or connection.

### 3. Configure Azure SQL authentication for HammerDB

The public deployment template uses Entra-only authentication by default. Configure HammerDB to connect from the benchmark VM through its system-assigned managed identity.

For an isolated benchmark server, run the following administration command from a terminal that has the repository, Azure CLI, and an Azure sign-in with permission to manage the deployed Azure SQL server. Your local terminal or Azure Cloud Shell are suitable; do not run it on the benchmark VM. Use the `azureSqlServerName` and `benchmarkVmName` deployment outputs, and omit `.database.windows.net` from the server name:

```bash
export AZURE_SUBSCRIPTION_ID="<subscription-id>"
export AZURE_RESOURCE_GROUP="<resource-group>"
export AZURE_SQL_SERVER_NAME="<server-name>"
export BENCHMARK_VM_NAME="<vm-name>"
scripts/provision/setup-azure-sql-vm-mi-admin.sh
```

The script reports the benchmark VM managed identity object ID. SSH to the benchmark VM and run the remaining commands there. Configure HammerDB to use Entra/MSI authentication and keep BCP disabled:

```bash
export AZURE_SQL_AUTH_MODE=entra
export AZURE_SQL_MSI_OBJECT_ID="<benchmark-vm-managed-identity-object-id>"
export AZURE_SQL_TPROC_C_DATABASE=tprocc
export AZURE_SQL_TPROC_C_USE_BCP=false

"${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-build-sqlserver-tprocc.tcl
```

Keep BCP disabled for this Entra-only configuration because the HammerDB BCP load path can attempt SQL authentication. The ODBC/MSI connection path uses the benchmark VM managed identity.

### 4. Prepare benchmark columns and marker table

Add benchmark-owned columns to `dbo.stock` before Fabric Mirroring starts. This ensures the large-update scenario is included in the first replication attempt rather than relying on post-mirroring schema changes for the largest table.

```bash
python3 scripts/provision/run-azure-sql-msi.py \
  --file scripts/provision/setup-tprocc-benchmark-columns-azure-sql.sql
```

Create the marker table used for controlled CDC visibility checks:

```bash
python3 scripts/provision/setup-azure-sql-cdc-marker-msi.py
```

`dbo.fabric_cdc_latency_marker` is benchmark-owned and is not an application table. Its primary key is `marker_id` (`uniqueidentifier`); `batch_id`, `operation_type`, `source_send_ts`, and `source_commit_ts` identify and timestamp each controlled change, and `payload` optionally sizes it. The marker test inserts a row, records the source commit timestamp, then polls for that exact ID in the SQL analytics endpoint. It measures end-to-end **CDC visibility after mirroring has started**; it does not measure the initial snapshot, schema-discovery work, or Fabric internal replication time.

### 5. Create the Azure SQL login and mapped database user

For a service-principal connection, first create the service-principal server login in `master`, then create its mapped database user and grant mirroring permissions. This is the required order: Directory Readers on the **Azure SQL server managed identity** resolves the service principal for `CREATE LOGIN ... FROM EXTERNAL PROVIDER`; the database helper then maps `CREATE USER ... FOR LOGIN` and grants permissions.

```bash
python3 scripts/provision/grant-azure-sql-master-entra-principal-msi.py
python3 scripts/provision/grant-azure-sql-fabric-entra-principal-msi.py
```

For an Organizational account connection, set the same `FABRIC_ENTRA_*` values to the approved Entra user or group and use the same two-step login/user flow. `FABRIC_REPLACE_CONTAINED_USER=true` is only for replacing a benchmark-owned mapped user.

```bash
export FABRIC_ENTRA_PRINCIPAL="<service-principal display name, UPN, or group>"
export FABRIC_ENTRA_OBJECT_ID="<Entra object ID>"
export FABRIC_ENTRA_PRINCIPAL_TYPE=E
```

The helper grants the permissions needed by Fabric Mirroring, including `SELECT`, `ALTER ANY EXTERNAL MIRROR`, `VIEW DATABASE PERFORMANCE STATE`, and `VIEW DATABASE SECURITY STATE`.

### 6. Create the Fabric mirrored database through the public API

Set `FABRIC_CREATE_CONNECTION=true` only if the source app credentials are available and a connection does not already exist. The script creates or reuses the workspace and connection, creates or reuses the mirrored database, starts it, waits for its SQL analytics endpoint, and writes non-secret endpoint settings to `results/fabric-mirror-setup.env`.

```bash
export FABRIC_CREATE_CONNECTION=true
export FABRIC_GRANT_BENCHMARK_VM_WORKSPACE_VIEWER=true
python3 scripts/provision/setup-fabric-items.py
source results/fabric-mirror-setup.env
```

`FABRIC_MIRROR_TABLES` controls the selected TPROC-C tables and `dbo.fabric_cdc_latency_marker`; set it empty to mirror all data. Enable the source's **add any new tables to replication** option only when testing the new-table scenario.

## Benchmark scenarios and test files

| Scenario | Purpose | Script or query file |
|---|---|---|
| Initial snapshot parity | Confirms the TPROC-C tables copied during the initial snapshot are visible with matching row counts. | `scripts/benchmark/measure-initial-sync.py` |
| Marker insert latency | Writes controlled marker rows to Azure SQL and polls Fabric until each marker appears. | `scripts/benchmark/run-cdc-latency-test.py` |
| New table auto-replication | Creates a new source table after mirroring starts and checks whether Fabric auto-adds it. | `scripts/benchmark/run-new-table-auto-replication-test.py` |
| Large stock update | Updates benchmark-owned columns on 100,000 rows in `dbo.stock` and waits for all updated rows in Fabric. | `scripts/benchmark/run-stock-bulk-update.py` |
| Small-table schema evolution | Adds a post-mirroring benchmark column to `dbo.warehouse`. | `scripts/provision/setup-tprocc-schema-evolution-azure-sql.sql` and `scripts/benchmark/check-fabric-table-schema.py` |
| Fabric status capture | Captures Fabric table mirroring status snapshots where the API is available. | `scripts/benchmark/capture-fabric-mirroring-status.py` |

## Run or modify the tests

`AZURE_SQL_SQLCMD_ARGS` is the complete `sqlcmd` argument string for the **source** Azure SQL database (for example, `-C -S <server> -d tprocc -G`). `FABRIC_SQLCMD_ARGS` is the equivalent string for the **target SQL analytics endpoint**; `setup-fabric-items.py` derives and writes it to `results/fabric-mirror-setup.env`.

On Linux, `sqlcmd -G` uses an Entra user authentication flow; it does **not** obtain the benchmark VM's managed-identity token. Use those variables only for an interactive operator session. For noninteractive validation on the benchmark VM, use ODBC/MSI: `run-azure-sql-msi.py` (and the Azure SQL MSI helpers) for the source, and the Fabric ODBC access-token path after granting the VM identity Fabric Viewer for the target. This keeps source and target noninteractive validation on ODBC/MSI rather than relying on `sqlcmd -G`.

The benchmark scripts are parameterized through command-line arguments and environment variables. Start with the default 10 TPROC-C warehouses, then change one variable at a time.

Useful knobs:

| Setting | Environment variable or argument | Default |
|---|---|---|
| TPROC-C size | `TPROC_C_WAREHOUSES` | `10` |
| Marker batches | `CDC_MARKER_BATCHES` | `60` |
| Marker write interval | `CDC_MARKER_INTERVAL_SECONDS` | `5` |
| Poll interval | `CDC_POLL_INTERVAL_SECONDS` | `5` for marker checks, `15` for some batch scenarios |
| Stock update size | `STOCK_UPDATE_BATCH_SIZE` / `--batch-size` | `100000` |
| New table rows | `NEW_TABLE_TEST_ROWS` / `--rows` | `1000` |

Example marker run for Azure SQL Database:

```bash
python3 scripts/benchmark/run-cdc-latency-test.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-marker-table dbo.fabric_cdc_latency_marker \
  --poll-seconds 1 \
  --batches 30
```

Example large-update run:

```bash
python3 scripts/benchmark/run-stock-bulk-update.py \
  --source-type azure-sql-db \
  --source-sqlcmd-args "$AZURE_SQL_SQLCMD_ARGS" \
  --batch-size 100000 \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-stock-table "dbo.stock" \
  --poll-seconds 1
```

For publication-quality numbers, run each scenario multiple times, keep the polling interval low, and save the raw CSV/JSON outputs with the Azure SQL SKU, Fabric capacity SKU, TPROC-C warehouse count, and time window.

## Measurement notes

The scripts measure **user-observed visibility** through the Fabric SQL analytics endpoint. They record the source commit timestamp, poll the SQL analytics endpoint, and record the first time the expected row or row count is visible.

That means each number is an observed upper bound, not an exact internal replication timestamp. If the poll interval is 15 seconds, the actual visibility could have happened up to 15 seconds before the script detected it. SQL analytics endpoint session freshness and Fabric status API refresh timing can also affect when a polling client observes the change.

For the most reliable comparison:

1. Use `--poll-seconds 1` for confirmation runs.
2. Reconnect or use fresh SQL analytics endpoint sessions during polling if stale reads are suspected.
3. Capture Fabric mirroring status snapshots during the same test window.
4. Repeat each scenario and publish min, p50, p95, and max instead of a single run.
5. Treat new-table auto-replication and schema evolution separately from row-level CDC, because they include control-plane/table-discovery work.

### Metadata refresh is a result-consistency step

After initial setup or a schema/table-selection change, refresh SQL analytics endpoint metadata before validating the resulting tables or columns:

```bash
python3 scripts/benchmark/refresh-fabric-sql-endpoint-metadata.py
```

Save the output with the run. A table result of `NotRun` together with a recent `lastSuccess` is not an error: it indicates no additional refresh was needed for that table. Do not invoke metadata refresh during marker-latency polling, because it is a result-consistency operation, not part of the CDC latency path.

## Reference benchmark results

### Initial snapshot

Verified initial-snapshot row-count parity:

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

### Post-mirroring scenarios

These results are reference observations from the documented configuration. Use them as a comparison point, not as service limits; capture and report results from your own environment.

| Scenario | Observed result |
|---|---:|
| Marker insert visibility | 78.6 seconds (one observation) |
| New table auto-replication, 1,000 rows | 151.9 seconds |
| `warehouse` schema evolution and 2 updated rows | 430.2 seconds |
| `stock` 100K-row update visibility | 174.2 seconds |

The new-table scenario confirmed that Fabric picked up `dbo.fabric_auto_table_125329_c687` automatically because **add any new tables to replication** was enabled.

The large-update scenario used the TPROC-C `stock` table. At 10 warehouses, `stock` contains 1,000,000 rows. The test updated 100,000 rows and Fabric showed all 100,000 updated rows after about 174 seconds from the last source update timestamp.

The 78.6-second marker value is one environment-specific observation, not a service guarantee. For comparable statistics, run each scenario with a 1-second poll interval and repeated trials, then report min, p50, p95, and max latency.

## Lessons learned

- Scale Azure SQL before starting HammerDB builds. Scaling during a build can interrupt ODBC sessions.
- For Azure SQL Entra-only configurations, HammerDB uses ODBC/MSI; keep the SQL Server BCP load path disabled because it can attempt SQL authentication.
- Fabric Organizational account authentication required the same Entra user to exist as a contained database user with mirroring permissions.
- Fabric mirroring status APIs and SQL analytics endpoint visibility can differ briefly.
- New-table auto-replication and schema evolution are useful operational tests, but they should not be interpreted as pure row-level CDC latency.
- Keep source-system posts separate as the benchmark series expands.

## References

- [Microsoft Fabric Mirroring overview and supported operational data sources](https://learn.microsoft.com/fabric/mirroring/overview)
- [Tutorial: Mirror Azure SQL Database in Microsoft Fabric](https://learn.microsoft.com/fabric/mirroring/azure-sql-database-tutorial)
- [Fabric Mirroring REST API](https://learn.microsoft.com/fabric/mirroring/mirrored-database-rest-api)
- [Microsoft Entra service principals with Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-service-principal-tutorial)
