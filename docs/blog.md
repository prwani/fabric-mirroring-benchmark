# Microsoft Fabric Mirroring Benchmark Blog Series

This repository tracks a benchmark series for Microsoft Fabric Mirroring across operational source systems. Each post uses the same benchmark shape where possible:

- HammerDB **TPROC-C** as the OLTP source workload.
- 10 warehouses as the default initial data load.
- Fabric mirrored database SQL endpoint as the measurement target.
- Controlled `fabric_cdc_latency_marker` rows for end-to-end CDC visibility.
- Source-specific notes only where deployment, authentication, or mirroring behavior differs.

## Posts

| Source system | Blog post | Status |
|---|---|---|
| Azure Database for PostgreSQL Flexible Server | [`blog-postgresql-tprocc.md`](blog-postgresql-tprocc.md) | Validated |
| Azure SQL Database | [`blog-azure-sql-db-tprocc.md`](blog-azure-sql-db-tprocc.md), [`blog-azure-sql-db-tprocc.html`](blog-azure-sql-db-tprocc.html) | Validated; HTML draft available for Tech Community publishing |

Future source systems should get their own post instead of replacing an existing one.
