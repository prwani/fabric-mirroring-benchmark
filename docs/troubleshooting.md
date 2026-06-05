# Troubleshooting

## Mirroring setup fails

- Confirm PostgreSQL Flexible Server is General Purpose or Memory Optimized, not Burstable.
- Confirm PostgreSQL version is 14 or later.
- Confirm system-assigned managed identity is enabled on the PostgreSQL server.
- Confirm `wal_level=logical`, `max_replication_slots`, and `max_wal_senders` are configured.
- Do not manually add `azure_cdc` to `azure.extensions`; it may not appear in the user-configurable allow-list. Use the Fabric mirroring setup experience/API to install or manage Fabric-specific CDC components where supported.
- Confirm Fabric capacity is running and assigned to the workspace.
- Use the Fabric Mirroring REST API or fabric-cli to check mirrored database start/stop/status if the portal UI is inconclusive.

## Tables are missing from the mirror

Fabric mirroring can exclude unsupported tables. For this benchmark, first check for missing primary keys:

```sql
SELECT n.nspname, c.relname
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname = 'public'
  AND NOT EXISTS (
    SELECT 1 FROM pg_index i
    WHERE i.indrelid = c.oid AND i.indisprimary
  );
```

## CDC latency looks wrong

- Marker latency uses the PostgreSQL commit timestamp and the polling host clock. Keep the VM synchronized with NTP and interpret sub-second results with clock-skew caution.
- Compare marker results with Fabric mirroring status/latency metrics where available.
- Capture PostgreSQL source metrics to correlate latency with CPU, IOPS, storage, WAL, and connection pressure.

## WAL or storage grows unexpectedly

Stop Fabric mirroring cleanly and check replication slots:

```sql
SELECT slot_name, active, restart_lsn, confirmed_flush_lsn
FROM pg_replication_slots;
```

Drop only confirmed orphaned slots:

```sql
SELECT pg_drop_replication_slot('slot_name');
```
