#!/usr/bin/env python3
"""Refresh a Fabric SQL analytics endpoint and record the per-table outcome."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.lib.fabric_api import FabricClient, access_token


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace-id",
        default=os.environ.get("FABRIC_WORKSPACE_ID"),
        required=os.environ.get("FABRIC_WORKSPACE_ID") is None,
    )
    parser.add_argument(
        "--sql-endpoint-id",
        default=os.environ.get("FABRIC_SQL_ANALYTICS_ENDPOINT_ID"),
        required=os.environ.get("FABRIC_SQL_ANALYTICS_ENDPOINT_ID") is None,
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=int(os.environ.get("FABRIC_SQL_ENDPOINT_REFRESH_TIMEOUT_MINUTES", "15")),
    )
    parser.add_argument(
        "--operation-timeout-seconds",
        type=int,
        default=int(os.environ.get("FABRIC_SQL_ENDPOINT_REFRESH_OPERATION_TIMEOUT_SECONDS", "1200")),
    )
    parser.add_argument(
        "--recreate-tables",
        action="store_true",
        help="Drop and recreate SQL analytics endpoint tables. Do not use for normal benchmark capture.",
    )
    parser.add_argument(
        "--output",
        default=os.environ.get("FABRIC_SQL_ENDPOINT_REFRESH_FILE", "results/fabric-sql-endpoint-refresh.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.timeout_minutes < 1:
        raise SystemExit("--timeout-minutes must be at least 1.")

    requested_at = utc_now()
    client = FabricClient(access_token())
    response = client.request(
        "POST",
        f"/workspaces/{args.workspace_id}/sqlEndpoints/{args.sql_endpoint_id}/refreshMetadata",
        {
            "recreateTables": args.recreate_tables,
            "timeout": {"timeUnit": "Minutes", "value": args.timeout_minutes},
        },
    )
    completed = client.wait_for_lro(response, args.operation_timeout_seconds)
    result = {
        "requestedAt": requested_at,
        "completedAt": utc_now(),
        "workspaceId": args.workspace_id,
        "sqlAnalyticsEndpointId": args.sql_endpoint_id,
        "recreateTables": args.recreate_tables,
        "tableSyncStatuses": completed.body,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

    failures = [
        table
        for table in completed.body.get("value", [])
        if table.get("status") == "Failure"
    ]
    if failures:
        print(f"{len(failures)} SQL analytics endpoint table refresh(es) did not succeed.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
