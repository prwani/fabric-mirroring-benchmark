# Architecture

```text
HammerDB VM
  -> Azure Database for PostgreSQL Flexible Server
      -> Fabric Mirroring
          -> Fabric mirrored database / OneLake tables
              -> Measurement queries and result summaries
```

Azure infrastructure is deployed with Bicep. Fabric capacity is an Azure resource, but Fabric workspace and mirrored database items are Fabric control-plane resources created through Fabric REST APIs or the Fabric portal.

## Region model

`swedencentral` is the default deployment region. All region choices are parameters or environment variables so readers can run in another supported region.

## Measurement model

Initial sync measures wall-clock time from starting Fabric mirroring to completion/status plus row-count parity between PostgreSQL and the mirrored target.

CDC latency uses controlled marker rows in PostgreSQL. The polling client queries the Fabric target until each marker appears and calculates observed latency. Platform metrics are captured alongside this:

- Azure Monitor for PostgreSQL source-side health such as CPU, memory, storage, connections, network bytes, and WAL/replication-related metrics where exposed.
- Fabric monitoring UI/API for mirroring status, sync progress, and replication latency where available in the tenant.

Marker-based latency remains the benchmark source of truth because it measures user-observable end-to-end freshness.

