#!/usr/bin/env python3
"""Run a large TPROC-C stock update and measure Fabric visibility."""

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


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def quote_nliteral(value: str) -> str:
    return "N'" + value.replace("'", "''") + "'"


def run_psql(conn: str, sql: str) -> str:
    result = subprocess.run(
        ["psql", conn, "-q", "-v", "ON_ERROR_STOP=1", "-Atc", sql],
        check=True,
        text=True,
        capture_output=True,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else ""


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
class StockUpdateResult:
    batch_id: str
    source_type: str
    source_table: str
    fabric_table: str
    requested_rows: int
    updated_rows: int
    rows_visible: int
    first_source_update_ts: str
    last_source_update_ts: str
    fabric_seen_ts: str
    latency_from_first_update_ms: float
    latency_from_last_update_ms: float
    timed_out: bool


def parse_source_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def update_postgres_stock(conn: str, batch_id: str, batch_size: int, payload_bytes: int) -> tuple[int, str, str]:
    sql = f"""
    WITH selected AS (
      SELECT ctid
      FROM public.stock
      ORDER BY s_w_id, s_i_id
      LIMIT {batch_size}
    ),
    updated AS (
      UPDATE public.stock s
      SET mirror_benchmark_update_batch = {quote_literal(batch_id)},
          mirror_benchmark_update_ts = clock_timestamp(),
          mirror_benchmark_payload = repeat('u', {payload_bytes})
      FROM selected
      WHERE s.ctid = selected.ctid
      RETURNING mirror_benchmark_update_ts
    )
    SELECT
      COUNT(*),
      to_char(MIN(mirror_benchmark_update_ts) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
      to_char(MAX(mirror_benchmark_update_ts) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
    FROM updated;
    """
    count, first_ts, last_ts = run_psql(conn, sql).split("|")
    return int(count), first_ts, last_ts


def update_azure_sql_stock(sqlcmd_args: str, batch_id: str, batch_size: int, payload_bytes: int) -> tuple[int, str, str]:
    sql = f"""
    DECLARE @updated TABLE(update_ts datetime2(7) NOT NULL);
    ;WITH selected AS (
      SELECT TOP ({batch_size}) *
      FROM dbo.stock
      ORDER BY s_w_id, s_i_id
    )
    UPDATE selected
    SET mirror_benchmark_update_batch = {quote_nliteral(batch_id)},
        mirror_benchmark_update_ts = SYSUTCDATETIME(),
        mirror_benchmark_payload = REPLICATE(N'u', {payload_bytes})
    OUTPUT inserted.mirror_benchmark_update_ts INTO @updated;

    SELECT
      COUNT(1),
      CONVERT(varchar(33), MIN(update_ts), 126) + 'Z',
      CONVERT(varchar(33), MAX(update_ts), 126) + 'Z'
    FROM @updated;
    """
    count, first_ts, last_ts = run_sqlcmd(sqlcmd_args, sql, separator="|").split("|")
    return int(count), first_ts, last_ts


def fabric_batch_count(sqlcmd_args: str, table: str, batch_id: str) -> int:
    sql = f"SELECT COUNT(*) FROM {table} WHERE mirror_benchmark_update_batch = {quote_nliteral(batch_id)};"
    return int(run_sqlcmd(sqlcmd_args, sql))


def wait_for_fabric(
    sqlcmd_args: str,
    table: str,
    batch_id: str,
    expected_rows: int,
    timeout_seconds: float,
    poll_seconds: float,
) -> tuple[int, datetime, bool]:
    deadline = time.monotonic() + timeout_seconds
    rows_visible = 0
    while time.monotonic() < deadline:
        rows_visible = fabric_batch_count(sqlcmd_args, table, batch_id)
        if rows_visible >= expected_rows:
            return rows_visible, utc_now(), False
        time.sleep(poll_seconds)
    return rows_visible, utc_now(), True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-type", choices=["postgresql", "azure-sql-db"], default=os.environ.get("SOURCE_TYPE", "postgresql"))
    parser.add_argument("--pg-conn", default=os.environ.get("POSTGRES_PSQL_CONN"))
    parser.add_argument("--source-sqlcmd-args", default=os.environ.get("AZURE_SQL_SQLCMD_ARGS"))
    parser.add_argument("--fabric-sqlcmd-args", default=os.environ.get("FABRIC_SQLCMD_ARGS"), required=os.environ.get("FABRIC_SQLCMD_ARGS") is None)
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("STOCK_UPDATE_BATCH_SIZE", "100000")))
    parser.add_argument("--payload-bytes", type=int, default=int(os.environ.get("STOCK_UPDATE_PAYLOAD_BYTES", "128")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("CDC_POLL_INTERVAL_SECONDS", "15")))
    parser.add_argument("--timeout-seconds", type=float, default=float(os.environ.get("STOCK_UPDATE_TIMEOUT_SECONDS", "3600")))
    parser.add_argument("--batch-id", default=os.environ.get("STOCK_UPDATE_BATCH_ID"))
    parser.add_argument("--fabric-stock-table", default=os.environ.get("FABRIC_STOCK_TABLE", f"{os.environ.get('FABRIC_SCHEMA', 'dbo')}.stock"))
    parser.add_argument("--output", default=os.environ.get("STOCK_UPDATE_RESULTS_FILE", "results/stock-bulk-update.csv"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.source_type == "postgresql" and not args.pg_conn:
        raise SystemExit("Provide --pg-conn or POSTGRES_PSQL_CONN for PostgreSQL stock updates.")
    if args.source_type == "azure-sql-db" and not args.source_sqlcmd_args:
        raise SystemExit("Provide --source-sqlcmd-args or AZURE_SQL_SQLCMD_ARGS for Azure SQL stock updates.")

    batch_id = args.batch_id or f"stock-update-{uuid4()}"
    if args.source_type == "azure-sql-db":
        updated_rows, first_ts, last_ts = update_azure_sql_stock(
            args.source_sqlcmd_args,
            batch_id,
            args.batch_size,
            args.payload_bytes,
        )
        source_table = "dbo.stock"
    else:
        updated_rows, first_ts, last_ts = update_postgres_stock(
            args.pg_conn,
            batch_id,
            args.batch_size,
            args.payload_bytes,
        )
        source_table = "public.stock"

    rows_visible, seen, timed_out = wait_for_fabric(
        args.fabric_sqlcmd_args,
        args.fabric_stock_table,
        batch_id,
        updated_rows,
        args.timeout_seconds,
        args.poll_seconds,
    )
    first_update = parse_source_ts(first_ts)
    last_update = parse_source_ts(last_ts)
    result = StockUpdateResult(
        batch_id=batch_id,
        source_type=args.source_type,
        source_table=source_table,
        fabric_table=args.fabric_stock_table,
        requested_rows=args.batch_size,
        updated_rows=updated_rows,
        rows_visible=rows_visible,
        first_source_update_ts=first_ts,
        last_source_update_ts=last_ts,
        fabric_seen_ts=iso(seen),
        latency_from_first_update_ms=(seen - first_update).total_seconds() * 1000,
        latency_from_last_update_ms=(seen - last_update).total_seconds() * 1000,
        timed_out=timed_out,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_header = not output.exists()
    with output.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[field for field in StockUpdateResult.__annotations__])
        if write_header:
            writer.writeheader()
        writer.writerow(result.__dict__)

    status = "timeout" if timed_out else "complete"
    print(
        f"{batch_id} rows={rows_visible}/{updated_rows} "
        f"latency_last_update_ms={result.latency_from_last_update_ms:.0f} {status}"
    )
    return 2 if timed_out else 0


if __name__ == "__main__":
    sys.exit(main())
