#!/usr/bin/env python3
"""Run batch insert/update CDC tests against the marker table.

This complements the single-row marker test by measuring how long a whole
batch takes to become visible in the Fabric SQL endpoint.
"""

from __future__ import annotations

import argparse
import csv
import os
import shlex
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


SQL_COPT_SS_ACCESS_TOKEN = 1256


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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

    def count_batch(self, table: str, batch_id: str, operation_type: str) -> int:
        sql = (
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE batch_id = '{batch_id}' AND operation_type = '{operation_type}';"
        )
        if self.sqlcmd_args:
            command = ["sqlcmd", *shlex.split(self.sqlcmd_args), "-Q", f"SET NOCOUNT ON; {sql}", "-h", "-1", "-W"]
            result = subprocess.run(command, check=True, text=True, capture_output=True)
            lines = [
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip() and not line.startswith("(") and set(line.strip()) != {"-"}
            ]
            return int(lines[-1])

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
            return int(cursor.fetchone()[0])


@dataclass
class BatchResult:
    batch_id: str
    operation_type: str
    batch_size: int
    rows_visible: int
    source_send_ts: str
    first_source_commit_ts: str
    last_source_commit_ts: str
    fabric_seen_ts: str
    latency_from_first_commit_ms: float
    latency_from_last_commit_ms: float
    timed_out: bool


def insert_batch(pg_conn: str, operation_type: str, batch_size: int, payload_bytes: int) -> tuple[str, str, str, str, float, float]:
    batch_id = f"{operation_type}-{uuid4()}"
    send_ts = iso(utc_now())
    sql = f"""
    WITH inserted AS (
      INSERT INTO public.fabric_cdc_latency_marker (batch_id, operation_type, source_send_ts, payload)
      SELECT {quote_literal(batch_id)}, {quote_literal(operation_type)}, {quote_literal(send_ts)}::timestamptz, repeat('x', {payload_bytes})
      FROM generate_series(1, {batch_size})
      RETURNING source_commit_ts
    )
    SELECT
      COUNT(*),
      MIN(source_commit_ts),
      MAX(source_commit_ts),
      EXTRACT(EPOCH FROM MIN(source_commit_ts)),
      EXTRACT(EPOCH FROM MAX(source_commit_ts))
    FROM inserted;
    """
    inserted, first_commit, last_commit, first_epoch, last_epoch = run_psql(pg_conn, sql).split("|")
    if int(inserted) != batch_size:
        raise RuntimeError(f"Expected {batch_size} inserted rows but PostgreSQL returned {inserted}.")
    return batch_id, send_ts, first_commit, last_commit, float(first_epoch), float(last_epoch)


def update_batch(pg_conn: str, batch_size: int, payload_bytes: int, fabric: FabricQuery, fabric_table: str, timeout_seconds: float, poll_seconds: float) -> tuple[str, str, str, str, float, float]:
    seed_batch_id, *_ = insert_batch(pg_conn, "bulk_update_seed", batch_size, payload_bytes)
    wait_for_batch(fabric, fabric_table, seed_batch_id, "bulk_update_seed", batch_size, timeout_seconds, poll_seconds)

    update_batch_id = f"bulk_update-{uuid4()}"
    send_ts = iso(utc_now())
    sql = f"""
    WITH updated AS (
      UPDATE public.fabric_cdc_latency_marker
      SET batch_id = {quote_literal(update_batch_id)},
          operation_type = 'bulk_update',
          source_send_ts = {quote_literal(send_ts)}::timestamptz,
          source_commit_ts = clock_timestamp(),
          payload = repeat('u', {payload_bytes})
      WHERE batch_id = {quote_literal(seed_batch_id)}
      RETURNING source_commit_ts
    )
    SELECT
      COUNT(*),
      MIN(source_commit_ts),
      MAX(source_commit_ts),
      EXTRACT(EPOCH FROM MIN(source_commit_ts)),
      EXTRACT(EPOCH FROM MAX(source_commit_ts))
    FROM updated;
    """
    updated, first_commit, last_commit, first_epoch, last_epoch = run_psql(pg_conn, sql).split("|")
    if int(updated) != batch_size:
        raise RuntimeError(f"Expected {batch_size} updated rows but PostgreSQL returned {updated}.")
    return update_batch_id, send_ts, first_commit, last_commit, float(first_epoch), float(last_epoch)


def wait_for_batch(
    fabric: FabricQuery,
    table: str,
    batch_id: str,
    operation_type: str,
    batch_size: int,
    timeout_seconds: float,
    poll_seconds: float,
) -> tuple[int, datetime, bool]:
    deadline = time.monotonic() + timeout_seconds
    rows_visible = 0
    while time.monotonic() < deadline:
        rows_visible = fabric.count_batch(table, batch_id, operation_type)
        if rows_visible >= batch_size:
            return rows_visible, utc_now(), False
        time.sleep(poll_seconds)
    return rows_visible, utc_now(), True


def run_batch(args: argparse.Namespace, fabric: FabricQuery, writer: csv.DictWriter[str]) -> BatchResult:
    operation_type = f"bulk_{args.operation}"
    if args.operation == "insert":
        batch_id, send_ts, first_commit, last_commit, first_epoch, last_epoch = insert_batch(
            args.pg_conn,
            operation_type,
            args.batch_size,
            args.payload_bytes,
        )
    else:
        batch_id, send_ts, first_commit, last_commit, first_epoch, last_epoch = update_batch(
            args.pg_conn,
            args.batch_size,
            args.payload_bytes,
            fabric,
            args.fabric_marker_table,
            args.timeout_seconds,
            args.poll_seconds,
        )

    rows_visible, seen, timed_out = wait_for_batch(
        fabric,
        args.fabric_marker_table,
        batch_id,
        operation_type,
        args.batch_size,
        args.timeout_seconds,
        args.poll_seconds,
    )
    result = BatchResult(
        batch_id=batch_id,
        operation_type=operation_type,
        batch_size=args.batch_size,
        rows_visible=rows_visible,
        source_send_ts=send_ts,
        first_source_commit_ts=first_commit,
        last_source_commit_ts=last_commit,
        fabric_seen_ts=iso(seen),
        latency_from_first_commit_ms=(seen.timestamp() - first_epoch) * 1000,
        latency_from_last_commit_ms=(seen.timestamp() - last_epoch) * 1000,
        timed_out=timed_out,
    )
    writer.writerow(result.__dict__)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-conn", default=os.environ.get("POSTGRES_PSQL_CONN"), required=os.environ.get("POSTGRES_PSQL_CONN") is None)
    parser.add_argument("--operation", choices=["insert", "update"], default=os.environ.get("CDC_BULK_OPERATION", "insert"))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("CDC_BULK_BATCH_SIZE", "500")))
    parser.add_argument("--batches", type=int, default=int(os.environ.get("CDC_BULK_BATCHES", "3")))
    parser.add_argument("--payload-bytes", type=int, default=int(os.environ.get("CDC_BULK_PAYLOAD_BYTES", "256")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("CDC_POLL_INTERVAL_SECONDS", "15")))
    parser.add_argument("--timeout-seconds", type=float, default=float(os.environ.get("CDC_BULK_TIMEOUT_SECONDS", "1800")))
    parser.add_argument("--fabric-marker-table", default=os.environ.get("FABRIC_MARKER_TABLE", "_public.fabric_cdc_latency_marker"))
    parser.add_argument("--fabric-sqlcmd-args", default=os.environ.get("FABRIC_SQLCMD_ARGS"))
    parser.add_argument("--fabric-odbc-server", default=os.environ.get("FABRIC_ODBC_SERVER"))
    parser.add_argument("--fabric-database", default=os.environ.get("FABRIC_DATABASE", "tprocc"))
    parser.add_argument(
        "--fabric-access-token-command",
        default=os.environ.get(
            "FABRIC_ACCESS_TOKEN_COMMAND",
            "az account get-access-token --resource https://database.windows.net/ --query accessToken -o tsv",
        ),
    )
    parser.add_argument("--output", default=os.environ.get("CDC_BULK_RESULTS_FILE", "results/cdc-bulk-latency.csv"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fabric = FabricQuery(args)

    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[field for field in BatchResult.__annotations__])
        writer.writeheader()
        for index in range(args.batches):
            result = run_batch(args, fabric, writer)
            fh.flush()
            status = "timeout" if result.timed_out else "complete"
            print(
                f"{index + 1}/{args.batches} {result.operation_type} {result.batch_id} "
                f"rows={result.rows_visible}/{result.batch_size} "
                f"latency_last_commit_ms={result.latency_from_last_commit_ms:.0f} {status}",
                flush=True,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
