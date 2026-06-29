# PostgreSQL source adapter

Status: implemented and live deployment validated.

## Azure resource

- Azure Database for PostgreSQL Flexible Server
- Default source type: `postgresql`
- Default SKU: `Standard_D2ds_v5`, `GeneralPurpose`
- Default version: PostgreSQL 16

## HammerDB workload

Use the PostgreSQL HammerDB TPROC-C scripts:

- `scripts/benchmark/hammerdb-build-tprocc.tcl`
- `scripts/benchmark/hammerdb-check-tprocc.tcl`
- `scripts/benchmark/hammerdb-run-tprocc.tcl`

Default initial load size is `TPROC_C_WAREHOUSES=10`. This creates transactional OLTP-shaped tables and supports a sustained write workload for CDC latency measurements.

After the HammerDB build and before Fabric mirroring, add benchmark-owned columns to `public.stock`:

```bash
psql "$POSTGRES_PSQL_CONN" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-tprocc-benchmark-columns-postgres.sql
```

Use those pre-mirrored columns for the large update scenario:

```bash
python3 scripts/benchmark/run-stock-bulk-update.py \
  --pg-conn "$POSTGRES_PSQL_CONN" \
  --batch-size 100000 \
  --fabric-sqlcmd-args "$FABRIC_SQLCMD_ARGS" \
  --fabric-stock-table "_public.stock"
```

For post-mirroring schema evolution, use the smaller `public.warehouse` table:

```bash
psql "$POSTGRES_PSQL_CONN" \
  -v ON_ERROR_STOP=1 \
  -f scripts/provision/setup-tprocc-schema-evolution-postgres.sql
```

## Fabric mirroring tutorial

<https://learn.microsoft.com/fabric/mirroring/azure-database-postgresql-tutorial>

## Notes

The template configures `wal_level=logical`, replication slots/senders, system-assigned managed identity, firewall access for Azure services, and firewall access from the benchmark VM.
