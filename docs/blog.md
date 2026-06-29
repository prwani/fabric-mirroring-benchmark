# Benchmarking Microsoft Fabric Mirroring with HammerDB TPROC-C

This draft tracks the current benchmark direction: use HammerDB **TPROC-C** as the source workload for Microsoft Fabric Mirroring tests.

TPROC-C is the right fit for this benchmark because Fabric mirroring sources are normally operational OLTP systems. It gives us both an initial data load and ongoing transactional insert/update activity for CDC latency measurement.

## Current benchmark shape

- Source systems: Azure Database for PostgreSQL Flexible Server and Azure SQL Database.
- Workload: HammerDB TPROC-C.
- Default scale: 10 warehouses.
- Measurement target: Fabric mirrored database SQL endpoint.
- Latency method: controlled `fabric_cdc_latency_marker` rows, measured from source commit timestamp to first visibility in Fabric.

## Reader flow

1. Deploy the selected Azure source, shared benchmark VM, Fabric capacity, networking, and monitoring.
2. Install HammerDB and source client tools on the benchmark VM.
3. Build the TPROC-C schema and data.
4. Create the CDC marker table after the HammerDB build.
5. Configure Fabric mirroring for the TPROC-C database.
6. Measure initial sync with source/Fabric row-count parity.
7. Run HammerDB TPROC-C and marker inserts together to measure CDC latency under OLTP pressure.
8. Summarize latency and platform metrics.

## Tables to mirror

Mirror all TPROC-C tables plus the marker table:

- `warehouse`
- `district`
- `customer`
- `history`
- `orders`
- `new_order`
- `order_line`
- `stock`
- `item`
- `fabric_cdc_latency_marker`

The final blog should be completed only after the TPROC-C-only PostgreSQL and Azure SQL DB paths are both validated end-to-end.
