#!/usr/bin/env python3
"""Capture Fabric mirrored database and table-level replication status."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.lib.fabric_api import FabricClient, access_token


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", default=os.environ.get("FABRIC_WORKSPACE_ID"), required=os.environ.get("FABRIC_WORKSPACE_ID") is None)
    parser.add_argument("--mirrored-database-id", default=os.environ.get("FABRIC_MIRRORED_DATABASE_ID"), required=os.environ.get("FABRIC_MIRRORED_DATABASE_ID") is None)
    parser.add_argument("--output", default=os.environ.get("FABRIC_STATUS_FILE", "results/fabric-mirroring-status.json"))
    return parser.parse_args()


def table_mirroring_status(client: FabricClient, base: str) -> dict:
    """Collect every page of table status because large mirrors are paginated."""

    tables: list[dict] = []
    continuation_token: str | None = None
    while True:
        path = f"{base}/getTablesMirroringStatus"
        if continuation_token:
            path = f"{path}?{urlencode({'continuationToken': continuation_token})}"
        response = client.request("POST", path, {})
        tables.extend(response.body.get("data", response.body.get("value", [])))
        continuation_token = response.body.get("continuationToken")
        if not continuation_token:
            return {"value": tables}


def main() -> int:
    args = parse_args()
    client = FabricClient(access_token())
    base = f"workspaces/{args.workspace_id}/mirroredDatabases/{args.mirrored_database_id}"
    payload = {
        "capturedAt": utc_now(),
        "mirroringStatus": client.request("POST", f"/{base}/getMirroringStatus", {}).body,
        "tablesMirroringStatus": table_mirroring_status(client, f"/{base}"),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
