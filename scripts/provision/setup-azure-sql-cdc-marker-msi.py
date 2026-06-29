#!/usr/bin/env python3
"""Create the Azure SQL CDC marker table using managed identity authentication."""

from __future__ import annotations

import os
import sys

import pyodbc


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    server = env("AZURE_SQL_HOST")
    database = os.environ.get("AZURE_SQL_TPROC_C_DATABASE") or env("AZURE_SQL_DATABASE", "tprocc")
    msi_object_id = env("AZURE_SQL_MSI_OBJECT_ID")
    driver = os.environ.get("AZURE_SQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")

    connection = (
        f"DRIVER={{{driver}}};"
        f"SERVER=tcp:{server},1433;"
        f"DATABASE={database};"
        "AUTHENTICATION=ActiveDirectoryMsi;"
        f"UID={msi_object_id};"
        "Encrypt=yes;"
        "TrustServerCertificate=no"
    )

    sql = """
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
    SELECT COUNT(*) FROM dbo.fabric_cdc_latency_marker;
    """

    with pyodbc.connect(connection, autocommit=True, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        while True:
            try:
                rows = cursor.fetchall()
                if rows:
                    print(f"dbo.fabric_cdc_latency_marker rows: {rows[-1][0]}")
            except pyodbc.ProgrammingError:
                pass
            if not cursor.nextset():
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
