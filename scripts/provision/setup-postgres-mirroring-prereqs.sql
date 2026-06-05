CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

CREATE TABLE IF NOT EXISTS public.fabric_cdc_latency_marker (
    marker_id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id text NOT NULL,
    operation_type text NOT NULL,
    source_send_ts timestamptz NOT NULL,
    source_commit_ts timestamptz NOT NULL DEFAULT clock_timestamp(),
    payload text NOT NULL DEFAULT repeat('x', 128)
);

COMMENT ON TABLE public.fabric_cdc_latency_marker IS 'Controlled marker table for Fabric mirroring CDC latency measurement.';
