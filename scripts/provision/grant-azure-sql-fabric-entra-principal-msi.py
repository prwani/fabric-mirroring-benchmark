#!/usr/bin/env python3
"""Grant Azure SQL mirroring permissions to an Entra principal using VM MSI.

This avoids Microsoft Graph directory lookup from Azure SQL by creating the
contained database user from the Entra object ID.
"""

from __future__ import annotations

import os
import sys

import pyodbc


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def bracket(identifier: str) -> str:
    return "[" + identifier.replace("]", "]]") + "]"


def principal_type() -> str:
    value = os.environ.get("FABRIC_ENTRA_PRINCIPAL_TYPE", "E").upper()
    if value not in {"E", "X"}:
        raise SystemExit("FABRIC_ENTRA_PRINCIPAL_TYPE must be E for user/app or X for group.")
    return value


def main() -> int:
    server = env("AZURE_SQL_HOST")
    database = os.environ.get("AZURE_SQL_TPROC_C_DATABASE") or env("AZURE_SQL_DATABASE", "tprocc")
    msi_object_id = env("AZURE_SQL_MSI_OBJECT_ID")
    principal_name = env("FABRIC_ENTRA_PRINCIPAL")
    principal_object_id = env("FABRIC_ENTRA_OBJECT_ID")
    principal_sql_type = principal_type()
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

    principal_literal = principal_name.replace("'", "''")
    quoted_principal = bracket(principal_name)
    sql = f"""
    IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{principal_literal}')
    BEGIN
      DECLARE @sid_hex nvarchar(34) =
        CONVERT(nvarchar(34), CONVERT(varbinary(16), CONVERT(uniqueidentifier, N'{principal_object_id}')), 1);
      DECLARE @create_sql nvarchar(max) =
        N'CREATE USER {quoted_principal} WITH SID = ' + @sid_hex + N', TYPE = {principal_sql_type}';
      EXEC sys.sp_executesql @create_sql;
    END;

    GRANT SELECT TO {quoted_principal};
    GRANT ALTER ANY EXTERNAL MIRROR TO {quoted_principal};
    GRANT VIEW DATABASE PERFORMANCE STATE TO {quoted_principal};
    GRANT VIEW DATABASE SECURITY STATE TO {quoted_principal};

    SELECT name, type_desc, CONVERT(nvarchar(34), sid, 1)
    FROM sys.database_principals
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
