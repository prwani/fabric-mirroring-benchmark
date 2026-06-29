IF COL_LENGTH(N'dbo.stock', N'mirror_benchmark_update_batch') IS NULL
BEGIN
  ALTER TABLE dbo.stock ADD mirror_benchmark_update_batch nvarchar(100) NULL;
END;

IF COL_LENGTH(N'dbo.stock', N'mirror_benchmark_update_ts') IS NULL
BEGIN
  ALTER TABLE dbo.stock ADD mirror_benchmark_update_ts datetime2(7) NULL;
END;

IF COL_LENGTH(N'dbo.stock', N'mirror_benchmark_payload') IS NULL
BEGIN
  ALTER TABLE dbo.stock ADD mirror_benchmark_payload nvarchar(4000) NULL;
END;

IF NOT EXISTS (
  SELECT 1
  FROM sys.indexes
  WHERE name = N'ix_stock_mirror_benchmark_update_batch'
    AND object_id = OBJECT_ID(N'dbo.stock')
)
BEGIN
  CREATE INDEX ix_stock_mirror_benchmark_update_batch
    ON dbo.stock (mirror_benchmark_update_batch);
END;
GO
