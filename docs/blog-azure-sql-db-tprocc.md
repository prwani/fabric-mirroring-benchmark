# Benchmarking Microsoft Fabric Mirroring with Azure SQL Database and HammerDB TPROC-C

This post covers the Azure SQL Database run in the Microsoft Fabric Mirroring benchmark series. PostgreSQL has its own post in [`blog-postgresql-tprocc.md`](blog-postgresql-tprocc.md).

The benchmark uses HammerDB **TPROC-C** because mirrored sources are usually operational OLTP systems. The same workload gives us an initial data load, ongoing transactional changes, and a large `stock` table for controlled update tests.

## Architecture

```text
HammerDB VM
  -> Azure SQL Database
      -> Microsoft Fabric Mirroring
          -> Fabric mirrored database SQL endpoint
              -> Row-count and CDC latency measurement
```

## Prerequisites

| Requirement | Notes |
|---|---|
| Azure subscription | Permission to deploy a new resource group, Azure SQL Database, VM, Fabric capacity, and monitoring resources. |
| Microsoft Fabric tenant | Permission to create mirrored database items. |
| Azure SQL supported tier | This run used vCore General Purpose. |
| Fabric Organizational account | Used for the mirrored database connection in this tenant. |
| Benchmark VM managed identity | Used by HammerDB to connect to Azure SQL under Entra-only authentication. |

Validated settings:

| Setting | Value |
|---|---|
| Region | `swedencentral` |
| Azure SQL server | `sql-fsqlmb-53vwnrvnudnko.database.windows.net` |
| Database | `tprocc` |
| SKU during final build | `GP_Gen5_4` |
| Workload | HammerDB TPROC-C |
| Scale | 10 warehouses |
| Build VUs | 4 |
| Fabric workspace | `fsqlmb-benchmark` |
| Mirrored database item | `tprocc` |
| SQL endpoint | `pindfi4msvfe7lkp6tm4de6jo4-pdoctk7rph7urpg5px4zdecfoi.datawarehouse.fabric.microsoft.com` |
| Mirroring option | Add any new tables to replication enabled |

## Steps

1. Deploy a fresh Azure SQL Database source:

   ```bash
   SOURCE_TYPE=azure-sql-db \
   AZURE_RESOURCE_GROUP=rg-fabric-sqldb-mirror-bench \
   PROJECT_NAME=fsqlmb \
   scripts/provision/deploy-azure.sh
   ```

2. For Entra-only tenants, set the VM managed identity as SQL Entra admin for this isolated benchmark server:

   ```bash
   export AZURE_SQL_SERVER_NAME="<server-name>"
   export BENCHMARK_VM_NAME="<vm-name>"
   scripts/provision/setup-azure-sql-vm-mi-admin.sh
   ```

3. Build TPROC-C with managed identity. Keep BCP disabled for Entra/MSI builds:

   ```bash
   export AZURE_SQL_AUTH_MODE=entra
   export AZURE_SQL_MSI_OBJECT_ID="<benchmark-vm-managed-identity-object-id>"
   export AZURE_SQL_TPROC_C_DATABASE=tprocc
   export AZURE_SQL_TPROC_C_USE_BCP=false

   "${HAMMERDB_CLI:-hammerdbcli}" auto scripts/benchmark/hammerdb-build-sqlserver-tprocc.tcl
   ```

4. Add benchmark-owned columns to `dbo.stock` before Fabric mirroring starts:

   ```bash
   sqlcmd $AZURE_SQL_SQLCMD_ARGS \
     -i scripts/provision/setup-tprocc-benchmark-columns-azure-sql.sql
   ```

5. Create the marker table:

   ```bash
   python3 scripts/provision/setup-azure-sql-cdc-marker-msi.py
   ```

6. Grant the Fabric Organizational account mirroring permissions in Azure SQL. If the SQL server identity lacks Directory Readers, grant by object ID:

   ```bash
   export FABRIC_ENTRA_PRINCIPAL="<UPN used in Fabric>"
   export FABRIC_ENTRA_OBJECT_ID="<Entra object ID>"
   export FABRIC_ENTRA_PRINCIPAL_TYPE=E
   python3 scripts/provision/grant-azure-sql-fabric-entra-principal-msi.py
   ```

7. In Fabric, create a mirrored Azure SQL Database item for `tprocc`, use Organizational account authentication, and enable **add any new tables to replication**.

8. Validate initial sync and run post-mirroring scenarios:

   - Marker insert latency.
   - New table auto-replication.
   - `warehouse` schema evolution.
   - 100K-row update on `stock`.

## Initial sync result

Row-count parity succeeded:

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

## Post-mirroring results

| Scenario | Result |
|---|---:|
| Marker insert visibility | 354.6 seconds |
| New table auto-replication, 1,000 rows | 151.9 seconds |
| `warehouse` schema evolution and 2 updated rows | 430.2 seconds |
| `stock` 100K-row update visibility | 174.2 seconds |

The new-table scenario confirmed that Fabric picked up `dbo.fabric_auto_table_125329_c687` automatically because **add any new tables to replication** was enabled.

The large-update scenario used the TPROC-C `stock` table. At 10 warehouses, `stock` contains 1,000,000 rows. The test updated 100,000 rows and Fabric showed all 100,000 updated rows after about 174 seconds from the source update timestamp.

## Lessons learned

- Scale Azure SQL before starting HammerDB builds. Scaling during a build can interrupt ODBC sessions.
- For Azure SQL Entra-only tenants, HammerDB works through ODBC/MSI, but the SQL Server BCP load path attempted SQL authentication in this validation. Keep `AZURE_SQL_TPROC_C_USE_BCP=false` unless your auth path supports BCP.
- Fabric Organizational account authentication required the same Entra user to exist as a contained database user with mirroring permissions.
- Fabric mirroring status APIs and Fabric SQL endpoint visibility can differ briefly. Reconnect SQL endpoint sessions between latency polling attempts.
- Keep source-system posts separate as the series expands.
