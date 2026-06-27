#!/usr/bin/env python3
"""Update many rows in TPROC-H lineitem and measure Fabric visibility.

The script updates benchmark-only columns so HammerDB's TPROC-H schema and
query semantics remain intact. It records a sample key that can be used with
Fabric Warehouse time-travel queries to compare old and new values.
"""

from __future__ import annotations

import argparse
import csv
import os
import shlex
import struct
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


SQL_COPT_SS_ACCESS_TOKEN = 1256


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_psql(conn: str, sql: str) -> str:
    result = subprocess.run(
        ["psql", conn, "-q", "-v", "ON_ERROR_STOP=1", "-Atc", sql],
        check=True,
        text=True,
        capture_output=True,
    )
    return next(line for line in result.stdout.splitlines() if line.strip())


def run_command(command: str) -> str:
    result = subprocess.run(shlex.split(command), check=True, text=True, capture_output=True)
    return result.stdout.strip()


class FabricQuery:
    def __init__(self, args: argparse.Namespace) -> None:
        self.sqlcmd_args = args.fabric_sqlcmd_args
        self.odbc_server = args.fabric_odbc_server
        self.odbc_database = args.fabric_database
        self.access_token_command = args.fabric_access_token_command
        if not self.sqlcmd_args and not self.odbc_server:
            raise ValueError("Provide either --fabric-sqlcmd-args or --fabric-odbc-server.")

    def scalar(self, sql: str) -> str:
        if self.sqlcmd_args:
            command = ["sqlcmd", *shlex.split(self.sqlcmd_args), "-Q", f"SET NOCOUNT ON; {sql}", "-h", "-1", "-W"]
            result = subprocess.run(command, check=True, text=True, capture_output=True)
            lines = [
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip() and not line.startswith("(") and set(line.strip()) != {"-"}
            ]
            return lines[-1]

        try:
            import pyodbc
        except ImportError as exc:
            raise RuntimeError("pyodbc is required when using --fabric-odbc-server.") from exc

        token = run_command(self.access_token_command)
        token_bytes = token.encode("utf-16-le")
        attrs = {SQL_COPT_SS_ACCESS_TOKEN: struct.pack("=i", len(token_bytes)) + token_bytes}
        conn_str = (
            "Driver={ODBC Driver 18 for SQL Server};"
            f"Server={self.odbc_server};"
            f"Database={self.odbc_database};"
            "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
        )
        with pyodbc.connect(conn_str, attrs_before=attrs, timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            row = cursor.fetchone()
            return str(row[0]) if row else ""

    def count_batch(self, table: str, batch_id: str) -> int:
        sql = f"SELECT COUNT(*) FROM {table} WHERE mirror_benchmark_update_batch = '{batch_id}';"
        return int(self.scalar(sql))


@dataclass
class LineitemBulkUpdateResult:
    batch_id: str
    requested_rows: int
    rows_updated: int
    rows_visible: int
    source_pre_update_ts: str
    first_source_update_ts: str
    last_source_update_ts: str
    fabric_seen_ts: str
    source_update_duration_ms: float
    latency_from_first_update_ms: float
    latency_from_last_update_ms: float
    sample_l_orderkey: int
    sample_l_linenumber: int
    timed_out: bool


def update_lineitem(pg_conn: str, rows: int, batch_id: str) -> tuple[int, str, str, float, float, int, int, float]:
    sql = f"""
    WITH target AS (
      SELECT ctid
      FROM public.lineitem
      WHERE mirror_benchmark_update_batch IS DISTINCT FROM {quote_literal(batch_id)}
      ORDER BY l_orderkey, l_linenumber
      LIMIT {rows}
    ),
    updated AS (
      UPDATE public.lineitem AS lineitem
      SET mirror_benchmark_update_ts = clock_timestamp(),
          mirror_benchmark_update_batch = {quote_literal(batch_id)}
      FROM target
      WHERE lineitem.ctid = target.ctid
      RETURNING lineitem.l_orderkey, lineitem.l_linenumber, lineitem.mirror_benchmark_update_ts
    )
    SELECT
      COUNT(*),
      MIN(mirror_benchmark_update_ts),
      MAX(mirror_benchmark_update_ts),
      EXTRACT(EPOCH FROM MIN(mirror_benchmark_update_ts)),
      EXTRACT(EPOCH FROM MAX(mirror_benchmark_update_ts)),
      (array_agg(l_orderkey ORDER BY l_orderkey, l_linenumber))[1],
      (array_agg(l_linenumber ORDER BY l_orderkey, l_linenumber))[1]
    FROM updated;
    """
    row = run_psql(pg_conn, sql).split("|")
    updated, first_ts, last_ts, first_epoch, last_epoch, sample_orderkey, sample_linenumber = row
    return (
        int(updated),
        first_ts,
        last_ts,
        float(first_epoch),
        float(last_epoch),
        int(sample_orderkey),
        int(sample_linenumber),
        (float(last_epoch) - float(first_epoch)) * 1000,
    )


def wait_for_fabric(fabric: FabricQuery, table: str, batch_id: str, expected_rows: int, timeout_seconds: float, poll_seconds: float) -> tuple[int, datetime, bool]:
    deadline = time.monotonic() + timeout_seconds
    rows_visible = 0
    while time.monotonic() < deadline:
        rows_visible = fabric.count_batch(table, batch_id)
        if rows_visible >= expected_rows:
            return rows_visible, datetime.now(timezone.utc), False
        time.sleep(poll_seconds)
    return rows_visible, datetime.now(timezone.utc), True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-conn", default=os.environ.get("POSTGRES_PSQL_CONN"), required=os.environ.get("POSTGRES_PSQL_CONN") is None)
    parser.add_argument("--rows", type=int, default=int(os.environ.get("LINEITEM_BULK_UPDATE_ROWS", "100000")))
    parser.add_argument("--batches", type=int, default=int(os.environ.get("LINEITEM_BULK_UPDATE_BATCHES", "1")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("CDC_POLL_INTERVAL_SECONDS", "30")))
    parser.add_argument("--timeout-seconds", type=float, default=float(os.environ.get("LINEITEM_BULK_UPDATE_TIMEOUT_SECONDS", "3600")))
    parser.add_argument("--fabric-lineitem-table", default=os.environ.get("FABRIC_LINEITEM_TABLE", "_public.lineitem"))
    parser.add_argument("--fabric-sqlcmd-args", default=os.environ.get("FABRIC_SQLCMD_ARGS"))
    parser.add_argument("--fabric-odbc-server", default=os.environ.get("FABRIC_ODBC_SERVER"))
    parser.add_argument("--fabric-database", default=os.environ.get("FABRIC_DATABASE", "tpch"))
    parser.add_argument(
        "--fabric-access-token-command",
        default=os.environ.get(
            "FABRIC_ACCESS_TOKEN_COMMAND",
            "az account get-access-token --resource https://database.windows.net/ --query accessToken -o tsv",
        ),
    )
    parser.add_argument("--output", default=os.environ.get("LINEITEM_BULK_UPDATE_RESULTS_FILE", "results/lineitem-bulk-update.csv"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fabric = FabricQuery(args)

    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[field for field in LineitemBulkUpdateResult.__annotations__])
        writer.writeheader()
        for index in range(args.batches):
            batch_id = f"lineitem-update-{uuid4()}"
            pre_update_ts = datetime.now(timezone.utc)
            rows_updated, first_ts, last_ts, first_epoch, last_epoch, sample_orderkey, sample_linenumber, update_duration_ms = update_lineitem(
                args.pg_conn,
                args.rows,
                batch_id,
            )
            rows_visible, fabric_seen_ts, timed_out = wait_for_fabric(
                fabric,
                args.fabric_lineitem_table,
                batch_id,
                rows_updated,
                args.timeout_seconds,
                args.poll_seconds,
            )
            result = LineitemBulkUpdateResult(
                batch_id=batch_id,
                requested_rows=args.rows,
                rows_updated=rows_updated,
                rows_visible=rows_visible,
                source_pre_update_ts=iso(pre_update_ts),
                first_source_update_ts=first_ts,
                last_source_update_ts=last_ts,
                fabric_seen_ts=iso(fabric_seen_ts),
                source_update_duration_ms=update_duration_ms,
                latency_from_first_update_ms=(fabric_seen_ts.timestamp() - first_epoch) * 1000,
                latency_from_last_update_ms=(fabric_seen_ts.timestamp() - last_epoch) * 1000,
                sample_l_orderkey=sample_orderkey,
                sample_l_linenumber=sample_linenumber,
                timed_out=timed_out,
            )
            writer.writerow(result.__dict__)
            fh.flush()
            status = "timeout" if result.timed_out else "complete"
            print(
                f"{index + 1}/{args.batches} {batch_id} rows={rows_visible}/{rows_updated} "
                f"latency_last_update_ms={result.latency_from_last_update_ms:.0f} {status}",
                flush=True,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
