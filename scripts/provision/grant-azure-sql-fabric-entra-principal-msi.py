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


def replace_contained_user() -> bool:
    value = os.environ.get("FABRIC_REPLACE_CONTAINED_USER", "false").lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    raise SystemExit("FABRIC_REPLACE_CONTAINED_USER must be true or false.")


def main() -> int:
    server = env("AZURE_SQL_HOST")
    database = os.environ.get("AZURE_SQL_TPROC_C_DATABASE") or env("AZURE_SQL_DATABASE", "tprocc")
    msi_object_id = env("AZURE_SQL_MSI_OBJECT_ID")
    principal_name = env("FABRIC_ENTRA_PRINCIPAL")
    env("FABRIC_ENTRA_OBJECT_ID")
    principal_type()
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
    with pyodbc.connect(connection, autocommit=True, timeout=30) as conn:
        cursor = conn.cursor()
        existing = cursor.execute(
            f"SELECT authentication_type_desc FROM sys.database_principals WHERE name = N'{principal_literal}';"
        ).fetchone()
        if existing:
            if not replace_contained_user():
                raise SystemExit(
                    f"Database user {principal_name!r} already exists as {existing[0]}. "
                    "Set FABRIC_REPLACE_CONTAINED_USER=true only when replacing a benchmark-owned user."
                )
            cursor.execute(f"DROP USER {quoted_principal};")

        cursor.execute(
            f"""
            CREATE USER {quoted_principal} FOR LOGIN {quoted_principal};
            GRANT SELECT TO {quoted_principal};
            GRANT ALTER ANY EXTERNAL MIRROR TO {quoted_principal};
            GRANT VIEW DATABASE PERFORMANCE STATE TO {quoted_principal};
            GRANT VIEW DATABASE SECURITY STATE TO {quoted_principal};
            SELECT name, type_desc, authentication_type_desc
            FROM sys.database_principals
            WHERE name = N'{principal_literal}';
            """
        )
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
