#!/usr/bin/env python3
"""Measure initial sync completion by polling row-count parity.

Start Fabric mirroring first, then run this script with the list of selected
tables. It records the time until Fabric table counts are at least the captured
PostgreSQL source counts.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_psql(conn: str, sql: str) -> str:
    result = subprocess.run(["psql", conn, "-v", "ON_ERROR_STOP=1", "-Atc", sql], check=True, text=True, capture_output=True)
    return result.stdout.strip()


def run_sqlcmd(sqlcmd_args: str, sql: str) -> str:
    command = ["sqlcmd", *shlex.split(sqlcmd_args), "-Q", f"SET NOCOUNT ON; {sql}", "-h", "-1", "-W"]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.startswith("(") and set(line.strip()) != {"-"}
    ]
    return lines[-1] if lines else "0"


def table_count_pg(conn: str, table: str) -> int:
    return int(run_psql(conn, f"SELECT COUNT(*) FROM {table};"))


def table_count_fabric(sqlcmd_args: str, table: str) -> int:
    return int(run_sqlcmd(sqlcmd_args, f"SELECT COUNT(*) FROM {table};"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-conn", default=os.environ.get("POSTGRES_PSQL_CONN"), required=os.environ.get("POSTGRES_PSQL_CONN") is None)
    parser.add_argument("--fabric-sqlcmd-args", default=os.environ.get("FABRIC_SQLCMD_ARGS"), required=os.environ.get("FABRIC_SQLCMD_ARGS") is None)
    parser.add_argument("--tables", default=os.environ.get("MIRRORED_TABLES", "public.region,public.nation,public.supplier,public.customer,public.part,public.partsupp,public.orders,public.lineitem,public.fabric_cdc_latency_marker"))
    parser.add_argument("--fabric-schema", default=os.environ.get("FABRIC_SCHEMA", "dbo"))
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("INITIAL_SYNC_POLL_SECONDS", "30")))
    parser.add_argument("--timeout-seconds", type=float, default=float(os.environ.get("INITIAL_SYNC_TIMEOUT_SECONDS", "14400")))
    parser.add_argument("--output", default=os.environ.get("INITIAL_SYNC_RESULTS_FILE", "results/initial-sync.json"))
    args = parser.parse_args()

    started_at = utc_now()
    source_counts: dict[str, int] = {}
    tables = [table.strip() for table in args.tables.split(",") if table.strip()]

    for table in tables:
        source_counts[table] = table_count_pg(args.pg_conn, table)

    deadline = time.monotonic() + args.timeout_seconds
    observations: list[dict[str, object]] = []

    while time.monotonic() < deadline:
        snapshot = {"observed_at": utc_now(), "tables": {}}
        complete = True
        for source_table, source_count in source_counts.items():
            table_name = source_table.split(".")[-1]
            fabric_table = f"{args.fabric_schema}.{table_name}"
            fabric_count = table_count_fabric(args.fabric_sqlcmd_args, fabric_table)
            snapshot["tables"][source_table] = {
                "source_count": source_count,
                "fabric_table": fabric_table,
                "fabric_count": fabric_count,
            }
            if fabric_count < source_count:
                complete = False
        observations.append(snapshot)
        print(json.dumps(snapshot))
        if complete:
            break
        time.sleep(args.poll_seconds)

    completed_at = utc_now() if observations and all(
        table["fabric_count"] >= table["source_count"]
        for table in observations[-1]["tables"].values()
    ) else None

    result = {
        "started_at": started_at,
        "completed_at": completed_at,
        "source_counts": source_counts,
        "observations": observations,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["observed_at", "source_table", "source_count", "fabric_table", "fabric_count"])
        for observation in observations:
            for source_table, counts in observation["tables"].items():
                writer.writerow([observation["observed_at"], source_table, counts["source_count"], counts["fabric_table"], counts["fabric_count"]])

    return 0 if completed_at else 2


if __name__ == "__main__":
    raise SystemExit(main())
