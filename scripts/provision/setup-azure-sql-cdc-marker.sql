IF OBJECT_ID(N'dbo.fabric_cdc_latency_marker', N'U') IS NULL
BEGIN
  CREATE TABLE dbo.fabric_cdc_latency_marker
  (
    marker_id uniqueidentifier NOT NULL
      CONSTRAINT DF_fabric_cdc_latency_marker_marker_id DEFAULT NEWID(),
    batch_id nvarchar(100) NOT NULL,
    operation_type nvarchar(20) NOT NULL,
    source_send_ts datetime2(7) NOT NULL,
    source_commit_ts datetime2(7) NOT NULL
      CONSTRAINT DF_fabric_cdc_latency_marker_source_commit_ts DEFAULT SYSUTCDATETIME(),
    payload nvarchar(max) NULL,
    CONSTRAINT PK_fabric_cdc_latency_marker PRIMARY KEY CLUSTERED (marker_id)
  );
END;
GO
