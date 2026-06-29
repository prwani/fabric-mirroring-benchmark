ALTER TABLE public.stock
    ADD COLUMN IF NOT EXISTS mirror_benchmark_update_batch text,
    ADD COLUMN IF NOT EXISTS mirror_benchmark_update_ts timestamptz,
    ADD COLUMN IF NOT EXISTS mirror_benchmark_payload text;

CREATE INDEX IF NOT EXISTS ix_stock_mirror_benchmark_update_batch
    ON public.stock (mirror_benchmark_update_batch);

COMMENT ON COLUMN public.stock.mirror_benchmark_update_batch IS 'Benchmark-only batch identifier used for large stock update CDC tests.';
COMMENT ON COLUMN public.stock.mirror_benchmark_update_ts IS 'Benchmark-only source update timestamp used for large stock update CDC tests.';
COMMENT ON COLUMN public.stock.mirror_benchmark_payload IS 'Benchmark-only payload used for large stock update CDC tests.';
