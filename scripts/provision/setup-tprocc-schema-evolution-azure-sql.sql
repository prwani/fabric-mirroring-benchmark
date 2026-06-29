IF COL_LENGTH(N'dbo.warehouse', N'mirror_schema_evolution_note') IS NULL
BEGIN
  ALTER TABLE dbo.warehouse ADD mirror_schema_evolution_note nvarchar(4000) NULL;
END;
GO
