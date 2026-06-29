ALTER TABLE public.warehouse
    ADD COLUMN IF NOT EXISTS mirror_schema_evolution_note text;

COMMENT ON COLUMN public.warehouse.mirror_schema_evolution_note IS 'Benchmark-only column added after mirroring starts to test schema evolution on a small table.';
