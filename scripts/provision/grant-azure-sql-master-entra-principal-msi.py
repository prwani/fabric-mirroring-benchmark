#!/usr/bin/env python3
"""Create an Azure SQL master user for a Fabric source Entra principal via VM MSI."""

from __future__ import annotations

import os
import sys

import pyodbc


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def bracket(identifier: str) -> str:
    return "[" + identifier.replace("]", "]]") + "]"


def main() -> int:
    server = env("AZURE_SQL_HOST")
    msi_object_id = env("AZURE_SQL_MSI_OBJECT_ID")
    principal_name = env("FABRIC_ENTRA_PRINCIPAL")
    principal_object_id = env("FABRIC_ENTRA_OBJECT_ID")
    driver = os.environ.get("AZURE_SQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
    connection = (
        f"DRIVER={{{driver}}};"
        f"SERVER=tcp:{server},1433;"
        "DATABASE=master;"
        "AUTHENTICATION=ActiveDirectoryMsi;"
        f"UID={msi_object_id};"
        "Encrypt=yes;"
        "TrustServerCertificate=no"
    )
    principal_literal = principal_name.replace("'", "''")
    quoted_principal = bracket(principal_name)
    sql = f"""
    IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'{principal_literal}')
    BEGIN
      CREATE LOGIN {quoted_principal} FROM EXTERNAL PROVIDER
        WITH OBJECT_ID = '{principal_object_id}';
    END;
    SELECT name, type_desc, CONVERT(nvarchar(34), sid, 1)
    FROM sys.server_principals
    WHERE name = N'{principal_literal}';
    """
    with pyodbc.connect(connection, autocommit=True, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        while True:
            try:
                for row in cursor.fetchall():
                    print(f"{row[0]}|{row[1]}|{row[2]}")
            except pyodbc.ProgrammingError:
                pass
            if not cursor.nextset():
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
