#!/usr/bin/env python3
"""Create Fabric workspace scaffolding and print mirroring setup guidance.

Fabric capacity is deployed by Bicep. Workspace and mirrored database items are
Fabric control-plane resources and may require tenant settings or delegated user
permissions, so this script is intentionally conservative.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


FABRIC_API = "https://api.fabric.microsoft.com/v1"


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def token() -> str:
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def fabric_request(method: str, path: str, access_token: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{FABRIC_API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Fabric API {method} {path} failed: {exc.code} {body}") from exc


def resolve_capacity_id(access_token: str, capacity_id_or_name: str) -> str:
    if "/" not in capacity_id_or_name and len(capacity_id_or_name) == 36:
        return capacity_id_or_name

    capacity_name = capacity_id_or_name.rstrip("/").split("/")[-1]
    response = fabric_request("GET", "/capacities", access_token)
    for capacity in response.get("value", []):
        if capacity.get("id") == capacity_id_or_name or capacity.get("displayName") == capacity_name:
            return capacity["id"]
    raise SystemExit(f"Could not resolve Fabric capacity GUID for {capacity_id_or_name}")


def find_workspace(access_token: str, display_name: str) -> dict | None:
    response = fabric_request("GET", "/workspaces", access_token)
    for item in response.get("value", []):
        if item.get("displayName") == display_name:
            return item
    return None


def main() -> int:
    workspace_name = env("FABRIC_WORKSPACE_NAME", "fpmb-benchmark")
    access_token = token()
    capacity_id = resolve_capacity_id(access_token, env("FABRIC_CAPACITY_ID"))

    workspace = find_workspace(access_token, workspace_name)
    if workspace is None:
        workspace = fabric_request(
            "POST",
            "/workspaces",
            access_token,
            {
                "displayName": workspace_name,
                "description": "Fabric mirroring benchmark workspace",
                "capacityId": capacity_id,
            },
        )

    print(json.dumps({"workspace": workspace}, indent=2))
    print()
    print("Next: create the source-specific mirrored database item through the Fabric Mirroring UI, Fabric REST API, or fabric-cli.")
    print("REST API: https://learn.microsoft.com/fabric/mirroring/mirrored-database-rest-api")
    print("fabric-cli start example: fab start <workspace>.Workspace/<mirror>.MirroredDatabase")
    print("fabric-cli stop example:  fab stop <workspace>.Workspace/<mirror>.MirroredDatabase")
    print("Record the workspaceId and mirroredDatabaseId in .env for measurement scripts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
