#!/usr/bin/env python3
"""Check whether expected columns are visible in a Fabric SQL endpoint table."""

from __future__ import annotations

import argparse
import os
import shlex
import struct
import subprocess


SQL_COPT_SS_ACCESS_TOKEN = 1256


def run_command(command: str) -> str:
    result = subprocess.run(shlex.split(command), check=True, text=True, capture_output=True)
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=os.environ.get("FABRIC_ODBC_SERVER"), required=os.environ.get("FABRIC_ODBC_SERVER") is None)
    parser.add_argument("--database", default=os.environ.get("FABRIC_DATABASE", "tpch"))
    parser.add_argument("--schema", required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--columns", required=True, help="Comma-separated expected column names.")
    parser.add_argument(
        "--access-token-command",
        default=os.environ.get(
            "FABRIC_ACCESS_TOKEN_COMMAND",
            "az account get-access-token --resource https://database.windows.net/ --query accessToken -o tsv",
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expected = {column.strip() for column in args.columns.split(",") if column.strip()}
    if not expected:
        raise ValueError("--columns must include at least one column.")

    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError("pyodbc is required for Fabric SQL endpoint schema checks.") from exc

    token = run_command(args.access_token_command)
    token_bytes = token.encode("utf-16-le")
    attrs = {SQL_COPT_SS_ACCESS_TOKEN: struct.pack("=i", len(token_bytes)) + token_bytes}
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={args.server};"
        f"Database={args.database};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    with pyodbc.connect(conn_str, attrs_before=attrs, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            """,
            args.schema,
            args.table,
        )
        visible = {row[0] for row in cursor.fetchall()}

    missing = sorted(expected - visible)
    print(f"visible={len(expected) - len(missing)}/{len(expected)}")
    if missing:
        print("missing=" + ",".join(missing))
        return 1
    print("all expected columns are visible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
