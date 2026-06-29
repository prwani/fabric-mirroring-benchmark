#!/usr/bin/env python3
"""Write source marker rows and poll a Fabric SQL endpoint for visibility.

The marker approach complements platform metrics:
- Azure Monitor captures source health, CPU, IOPS, and connections.
- Fabric monitoring surfaces mirror status/replication progress where available.
- This script calculates an end-to-end user-observed latency for controlled rows.
"""

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


def run_psql(conn: str, sql: str) -> str:
    result = subprocess.run(
        ["psql", conn, "-v", "ON_ERROR_STOP=1", "-Atc", sql],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


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
class MarkerResult:
    batch_id: str
    marker_id: str
    source_send_ts: str
    source_commit_ts: str
    fabric_seen_ts: str
    latency_ms: float


def insert_marker(pg_conn: str, batch_id: str) -> tuple[str, str, str]:
    send_ts = iso(utc_now())
    sql = f"""
    INSERT INTO public.fabric_cdc_latency_marker (batch_id, operation_type, source_send_ts, payload)
    VALUES ('{batch_id}', 'insert', '{send_ts}'::timestamptz, repeat('x', 256))
    RETURNING marker_id, source_send_ts, source_commit_ts;
    """
    marker_id, source_send_ts, source_commit_ts = run_psql(pg_conn, sql).split("|")
    return marker_id, source_send_ts, source_commit_ts


def insert_marker_sqlserver(sqlcmd_args: str, batch_id: str) -> tuple[str, str, str]:
    send_ts = iso(utc_now())
    sql = f"""
    INSERT INTO dbo.fabric_cdc_latency_marker (batch_id, operation_type, source_send_ts, payload)
    OUTPUT
      CONVERT(varchar(36), inserted.marker_id),
      CONVERT(varchar(33), inserted.source_send_ts, 126) + 'Z',
      CONVERT(varchar(33), inserted.source_commit_ts, 126) + 'Z'
    VALUES (N'{batch_id}', N'insert', CONVERT(datetime2(7), '{send_ts}', 127), REPLICATE(N'x', 256));
    """
    marker_id, source_send_ts, source_commit_ts = run_sqlcmd(sqlcmd_args, sql, separator="|").split("|")
    return marker_id, source_send_ts, source_commit_ts


def marker_visible(sqlcmd_args: str, marker_id: str, table_name: str) -> bool:
    sql = f"SELECT COUNT(*) FROM {table_name} WHERE CAST(marker_id AS varchar(36)) = '{marker_id}';"
    return run_sqlcmd(sqlcmd_args, sql).strip() == "1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-type", choices=["postgresql", "azure-sql-db"], default=os.environ.get("SOURCE_TYPE", "postgresql"))
    parser.add_argument("--pg-conn", default=os.environ.get("POSTGRES_PSQL_CONN"))
    parser.add_argument("--source-sqlcmd-args", default=os.environ.get("AZURE_SQL_SQLCMD_ARGS"))
    parser.add_argument("--fabric-sqlcmd-args", default=os.environ.get("FABRIC_SQLCMD_ARGS"), required=os.environ.get("FABRIC_SQLCMD_ARGS") is None)
    parser.add_argument("--fabric-marker-table", default=os.environ.get("FABRIC_MARKER_TABLE", "dbo.fabric_cdc_latency_marker"))
    parser.add_argument("--batches", type=int, default=int(os.environ.get("CDC_MARKER_BATCHES", "60")))
    parser.add_argument("--interval-seconds", type=float, default=float(os.environ.get("CDC_MARKER_INTERVAL_SECONDS", "5")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("CDC_POLL_INTERVAL_SECONDS", "5")))
    parser.add_argument("--timeout-seconds", type=float, default=float(os.environ.get("CDC_MARKER_TIMEOUT_SECONDS", "600")))
    parser.add_argument("--output", default=os.environ.get("CDC_RESULTS_FILE", "results/cdc-latency.csv"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.source_type == "postgresql" and not args.pg_conn:
        raise SystemExit("Provide --pg-conn or POSTGRES_PSQL_CONN for PostgreSQL marker writes.")
    if args.source_type == "azure-sql-db" and not args.source_sqlcmd_args:
        raise SystemExit("Provide --source-sqlcmd-args or AZURE_SQL_SQLCMD_ARGS for Azure SQL marker writes.")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[field for field in MarkerResult.__annotations__])
        writer.writeheader()

        for _ in range(args.batches):
            batch_id = f"batch-{uuid4()}"
            if args.source_type == "azure-sql-db":
                marker_id, source_send_ts, source_commit_ts = insert_marker_sqlserver(args.source_sqlcmd_args, batch_id)
            else:
                marker_id, source_send_ts, source_commit_ts = insert_marker(args.pg_conn, batch_id)
            deadline = time.monotonic() + args.timeout_seconds

            while time.monotonic() < deadline:
                if marker_visible(args.fabric_sqlcmd_args, marker_id, args.fabric_marker_table):
                    seen = utc_now()
                    committed = datetime.fromisoformat(source_commit_ts.replace("Z", "+00:00"))
                    result = MarkerResult(
                        batch_id=batch_id,
                        marker_id=marker_id,
                        source_send_ts=source_send_ts,
                        source_commit_ts=source_commit_ts,
                        fabric_seen_ts=iso(seen),
                        latency_ms=(seen - committed).total_seconds() * 1000,
                    )
                    writer.writerow(result.__dict__)
                    fh.flush()
                    print(f"{batch_id} {marker_id} {result.latency_ms:.0f} ms")
                    break
                time.sleep(args.poll_seconds)
            else:
                print(f"Timed out waiting for marker {marker_id}", file=sys.stderr)

            time.sleep(args.interval_seconds)

    return 0


if __name__ == "__main__":
    sys.exit(main())
