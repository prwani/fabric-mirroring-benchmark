#!/usr/bin/env python3
"""Capture Fabric mirrored database and table-level replication status."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def access_token() -> str:
    return subprocess.check_output(
        [
            "az",
            "account",
            "get-access-token",
            "--resource",
            "https://api.fabric.microsoft.com",
            "--query",
            "accessToken",
            "-o",
            "tsv",
        ],
        text=True,
    ).strip()


def fabric_post(path: str, token: str) -> dict:
    request = Request(
        f"https://api.fabric.microsoft.com/v1/{path}",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"Fabric API failed: {exc.code} {body}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", default=os.environ.get("FABRIC_WORKSPACE_ID"), required=os.environ.get("FABRIC_WORKSPACE_ID") is None)
    parser.add_argument("--mirrored-database-id", default=os.environ.get("FABRIC_MIRRORED_DATABASE_ID"), required=os.environ.get("FABRIC_MIRRORED_DATABASE_ID") is None)
    parser.add_argument("--output", default=os.environ.get("FABRIC_STATUS_FILE", "results/fabric-mirroring-status.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = access_token()
    base = f"workspaces/{args.workspace_id}/mirroredDatabases/{args.mirrored_database_id}"
    payload = {
        "capturedAt": utc_now(),
        "mirroringStatus": fabric_post(f"{base}/getMirroringStatus", token),
        "tablesMirroringStatus": fabric_post(f"{base}/getTablesMirroringStatus", token),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
