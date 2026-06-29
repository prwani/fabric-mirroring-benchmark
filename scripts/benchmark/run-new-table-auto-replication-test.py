#!/usr/bin/env python3
"""Create a new source table and wait for Fabric mirroring to auto-add it."""

from __future__ import annotations

import argparse
import csv
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def quote_identifier(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def run_sqlcmd(sqlcmd_args: str, sql: str, separator: str | None = None) -> str:
    command = ["sqlcmd", *shlex.split(sqlcmd_args), "-Q", f"SET NOCOUNT ON; {sql}", "-h", "-1", "-W"]
    if separator:
        command.extend(["-s", separator])
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.startswith("(") and set(line.strip()) != {"-"}
    ]
    return lines[-1] if lines else ""


@dataclass
class NewTableResult:
    table_name: str
    source_created_ts: str
    source_rows: int
    fabric_table: str
    fabric_seen_ts: str
    fabric_rows: int
    latency_ms: float
    timed_out: bool


def create_azure_sql_table(sqlcmd_args: str, table_name: str, rows: int) -> tuple[str, int]:
    table = quote_identifier(table_name)
    sql = f"""
    IF OBJECT_ID(N'dbo.{table_name}', N'U') IS NOT NULL
      DROP TABLE dbo.{table};

    CREATE TABLE dbo.{table}
    (
      id int NOT NULL CONSTRAINT PK_{table_name} PRIMARY KEY,
      source_created_ts datetime2(7) NOT NULL CONSTRAINT DF_{table_name}_source_created_ts DEFAULT SYSUTCDATETIME(),
      payload nvarchar(200) NOT NULL
    );

    ;WITH n AS (
      SELECT TOP ({rows}) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS id
      FROM sys.all_objects a CROSS JOIN sys.all_objects b
    )
    INSERT INTO dbo.{table} (id, payload)
    SELECT id, CONCAT(N'auto-new-table-', id)
    FROM n;

    SELECT
      CONVERT(varchar(33), MIN(source_created_ts), 126) + 'Z',
      COUNT(1)
    FROM dbo.{table};
    """
    created_ts, count = run_sqlcmd(sqlcmd_args, sql, separator="|").split("|")
    return created_ts, int(count)


def fabric_count(sqlcmd_args: str, table_name: str) -> int | None:
    table = quote_identifier(table_name)
    exists_sql = f"""
    SELECT COUNT(1)
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = '{table_name}';
    """
    if run_sqlcmd(sqlcmd_args, exists_sql) != "1":
        return None
    return int(run_sqlcmd(sqlcmd_args, f"SELECT COUNT(*) FROM dbo.{table};"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-type", choices=["azure-sql-db"], default=os.environ.get("SOURCE_TYPE", "azure-sql-db"))
    parser.add_argument("--source-sqlcmd-args", default=os.environ.get("AZURE_SQL_SQLCMD_ARGS"), required=os.environ.get("AZURE_SQL_SQLCMD_ARGS") is None)
    parser.add_argument("--fabric-sqlcmd-args", default=os.environ.get("FABRIC_SQLCMD_ARGS"), required=os.environ.get("FABRIC_SQLCMD_ARGS") is None)
    parser.add_argument("--table-name", default=os.environ.get("NEW_TABLE_TEST_NAME", f"fabric_auto_table_{uuid4().hex[:8]}"))
    parser.add_argument("--rows", type=int, default=int(os.environ.get("NEW_TABLE_TEST_ROWS", "1000")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("CDC_POLL_INTERVAL_SECONDS", "15")))
    parser.add_argument("--timeout-seconds", type=float, default=float(os.environ.get("NEW_TABLE_TEST_TIMEOUT_SECONDS", "1800")))
    parser.add_argument("--output", default=os.environ.get("NEW_TABLE_TEST_RESULTS_FILE", "results/new-table-auto-replication.csv"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_created_ts, source_rows = create_azure_sql_table(args.source_sqlcmd_args, args.table_name, args.rows)
    source_created = datetime.fromisoformat(source_created_ts.replace("Z", "+00:00"))
    deadline = time.monotonic() + args.timeout_seconds
    fabric_rows = 0
    timed_out = True
    seen = utc_now()

    while time.monotonic() < deadline:
        count = fabric_count(args.fabric_sqlcmd_args, args.table_name)
        if count is not None:
            fabric_rows = count
            if fabric_rows >= source_rows:
                seen = utc_now()
                timed_out = False
                break
        time.sleep(args.poll_seconds)

    result = NewTableResult(
        table_name=args.table_name,
        source_created_ts=source_created_ts,
        source_rows=source_rows,
        fabric_table=f"dbo.{args.table_name}",
        fabric_seen_ts=iso(seen),
        fabric_rows=fabric_rows,
        latency_ms=(seen - source_created).total_seconds() * 1000,
        timed_out=timed_out,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_header = not output.exists()
    with output.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[field for field in NewTableResult.__annotations__])
        if write_header:
            writer.writeheader()
        writer.writerow(result.__dict__)

    status = "timeout" if timed_out else "complete"
    print(
        f"{args.table_name} rows={fabric_rows}/{source_rows} "
        f"latency_ms={result.latency_ms:.0f} {status}"
    )
    return 2 if timed_out else 0


if __name__ == "__main__":
    sys.exit(main())
