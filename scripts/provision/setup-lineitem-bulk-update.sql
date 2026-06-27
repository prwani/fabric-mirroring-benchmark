ALTER TABLE public.lineitem
    ADD COLUMN IF NOT EXISTS mirror_benchmark_update_ts timestamptz;

ALTER TABLE public.lineitem
    ADD COLUMN IF NOT EXISTS mirror_benchmark_update_batch text;

COMMENT ON COLUMN public.lineitem.mirror_benchmark_update_ts IS
    'Timestamp written by the Fabric mirroring benchmark bulk-update scenario.';

COMMENT ON COLUMN public.lineitem.mirror_benchmark_update_batch IS
    'Batch identifier written by the Fabric mirroring benchmark bulk-update scenario.';
