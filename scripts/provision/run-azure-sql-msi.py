#!/usr/bin/env python3
"""Execute an Azure SQL script through the benchmark VM managed identity."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import pyodbc


GO_BATCH_SEPARATOR = re.compile(r"(?im)^\s*GO\s*(?:--.*)?$")


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def connection_string() -> str:
    server = env("AZURE_SQL_HOST")
    database = os.environ.get("AZURE_SQL_TPROC_C_DATABASE") or env("AZURE_SQL_DATABASE", "tprocc")
    msi_object_id = env("AZURE_SQL_MSI_OBJECT_ID")
    driver = os.environ.get("AZURE_SQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER=tcp:{server},1433;"
        f"DATABASE={database};"
        "AUTHENTICATION=ActiveDirectoryMsi;"
        f"UID={msi_object_id};"
        "Encrypt=yes;"
        "TrustServerCertificate=no"
    )


def execute_file(sql_file: Path) -> None:
    sql = sql_file.read_text(encoding="utf-8")
    batches = [batch.strip() for batch in GO_BATCH_SEPARATOR.split(sql) if batch.strip()]
    with pyodbc.connect(connection_string(), autocommit=True, timeout=30) as conn:
        cursor = conn.cursor()
        for index, batch in enumerate(batches, start=1):
            cursor.execute(batch)
            while True:
                try:
                    for row in cursor.fetchall():
                        print("|".join(str(value) for value in row))
                except pyodbc.ProgrammingError:
                    pass
                if not cursor.nextset():
                    break
            print(f"Completed Azure SQL MSI batch {index}/{len(batches)} from {sql_file.name}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True, help="Azure SQL script file to execute.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.file.is_file():
        raise SystemExit(f"SQL script does not exist: {args.file}")
    execute_file(args.file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
