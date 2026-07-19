#!/usr/bin/env python3
"""Provision Fabric workspace and Azure SQL Database mirroring through public APIs."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.lib.fabric_api import FabricApiError, FabricClient, access_token


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def optional_env(name: str) -> str | None:
    return os.environ.get(name) or None


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    if value.lower() in {"1", "true", "yes"}:
        return True
    if value.lower() in {"0", "false", "no"}:
        return False
    raise SystemExit(f"{name} must be true or false.")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_tables(value: str | None) -> list[dict[str, Any]]:
    """Convert comma-separated schema.table names into mirroring table definitions."""

    if not value:
        return []
    tables: list[dict[str, Any]] = []
    for item in value.split(","):
        table = item.strip()
        if not table:
            continue
        schema_name, separator, table_name = table.partition(".")
        if not separator or not schema_name or not table_name or "." in table_name:
            raise SystemExit(
                "FABRIC_MIRROR_TABLES must contain comma-separated schema.table values, "
                f"but received {table!r}."
            )
        tables.append(
            {
                "source": {
                    "typeProperties": {
                        "schemaName": schema_name,
                        "tableName": table_name,
                    }
                }
            }
        )
    return tables


def build_mirroring_definition(
    connection_id: str,
    default_schema: str,
    mounted_tables: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the public ``mirroring.json`` definition for Azure SQL Database."""

    properties: dict[str, Any] = {
        "source": {
            "type": "AzureSqlDatabase",
            "typeProperties": {"connection": connection_id},
        },
        "target": {
            "type": "MountedRelationalDatabase",
            "typeProperties": {"format": "Delta", "defaultSchema": default_schema},
        },
    }
    if mounted_tables:
        properties["mountedTables"] = mounted_tables
    return {"properties": properties}


def build_connection_request() -> dict[str, Any]:
    """Build a Fabric cloud SQL connection request for an Azure SQL source app."""

    secret = optional_env("FABRIC_SOURCE_SERVICE_PRINCIPAL_SECRET")
    key_vault_connection_id = optional_env("FABRIC_KEY_VAULT_CONNECTION_ID")
    key_vault_secret_name = optional_env("FABRIC_KEY_VAULT_SECRET_NAME")
    if bool(secret) == bool(key_vault_connection_id):
        raise SystemExit(
            "Provide exactly one of FABRIC_SOURCE_SERVICE_PRINCIPAL_SECRET or "
            "FABRIC_KEY_VAULT_CONNECTION_ID plus FABRIC_KEY_VAULT_SECRET_NAME."
        )
    if key_vault_connection_id and not key_vault_secret_name:
        raise SystemExit("FABRIC_KEY_VAULT_SECRET_NAME is required with FABRIC_KEY_VAULT_CONNECTION_ID.")

    credentials: dict[str, Any] = {
        "credentialType": "ServicePrincipal",
        "tenantId": env("FABRIC_SOURCE_TENANT_ID"),
        "servicePrincipalClientId": env("FABRIC_SOURCE_SERVICE_PRINCIPAL_CLIENT_ID"),
    }
    if secret:
        credentials["servicePrincipalSecret"] = secret
    else:
        secret_reference: dict[str, str] = {
            "connectionId": key_vault_connection_id or "",
            "secretName": key_vault_secret_name or "",
        }
        key_vault_secret_version = optional_env("FABRIC_KEY_VAULT_SECRET_VERSION")
        if key_vault_secret_version:
            secret_reference["version"] = key_vault_secret_version
        credentials["servicePrincipalSecretReference"] = secret_reference

    return {
        "connectivityType": "ShareableCloud",
        "displayName": env("FABRIC_CONNECTION_DISPLAY_NAME", "azure-sql-mirroring"),
        "connectionDetails": {
            "type": "SQL",
            "creationMethod": "SQL",
            "parameters": [
                {"name": "server", "dataType": "Text", "value": env("AZURE_SQL_HOST")},
                {"name": "database", "dataType": "Text", "value": env("AZURE_SQL_DATABASE")},
            ],
        },
        "privacyLevel": "Organizational",
        "credentialDetails": {
            "singleSignOnType": "None",
            "connectionEncryption": "Encrypted",
            "skipTestConnection": False,
            "credentials": credentials,
        },
    }


def resolve_capacity_id(client: FabricClient, capacity_id_or_name: str) -> str:
    if "/" not in capacity_id_or_name and len(capacity_id_or_name) == 36:
        return capacity_id_or_name

    capacity_name = capacity_id_or_name.rstrip("/").split("/")[-1]
    for capacity in client.list_values("/capacities"):
        if capacity.get("id") == capacity_id_or_name or capacity.get("displayName") == capacity_name:
            return capacity["id"]
    raise SystemExit(f"Could not resolve Fabric capacity GUID for {capacity_id_or_name}")


def find_workspace(client: FabricClient, display_name: str) -> dict[str, Any] | None:
    for workspace in client.list_values("/workspaces"):
        if workspace.get("displayName") == display_name:
            return workspace
    return None


def find_connection(client: FabricClient, display_name: str, server: str, database: str) -> dict[str, Any] | None:
    expected_path = f"{server};{database}".lower()
    for connection in client.list_values("/connections"):
        details = connection.get("connectionDetails", {})
        if (
            connection.get("displayName") == display_name
            and details.get("type") == "SQL"
            and details.get("path", "").lower() == expected_path
        ):
            return connection
    return None


def find_mirror(client: FabricClient, workspace_id: str, display_name: str) -> dict[str, Any] | None:
    for mirror in client.list_values(f"/workspaces/{workspace_id}/mirroredDatabases"):
        if mirror.get("displayName") == display_name:
            return mirror
    return None


def sqlcmd_args_from_connection_string(connection_string: str, default_database: str | None = None) -> str | None:
    """Convert a Fabric TDS connection string to the Entra sqlcmd arguments used here."""

    if "=" not in connection_string:
        if not default_database:
            return None
        return f"-C -S {connection_string.strip()} -d {default_database} -G"

    properties: dict[str, str] = {}
    for part in connection_string.split(";"):
        key, separator, value = part.partition("=")
        if separator:
            properties[key.strip().lower()] = value.strip()
    server = properties.get("data source") or properties.get("server")
    database = properties.get("initial catalog") or properties.get("database")
    if not server or not database:
        return None
    return f"-C -S {server} -d {database} -G"


def get_sql_endpoint_properties(client: FabricClient, workspace_id: str, mirror_id: str) -> dict[str, Any]:
    mirror = client.request("GET", f"/workspaces/{workspace_id}/mirroredDatabases/{mirror_id}").body
    return mirror.get("properties", {}).get("sqlEndpointProperties", {})


def mirroring_status(client: FabricClient, workspace_id: str, mirror_id: str) -> str:
    status = client.request(
        "POST",
        f"/workspaces/{workspace_id}/mirroredDatabases/{mirror_id}/getMirroringStatus",
        {},
    ).body.get("status")
    if not status:
        raise RuntimeError(f"Fabric did not return a mirroring status for {mirror_id}.")
    return status


def wait_for_startable_status(client: FabricClient, workspace_id: str, mirror_id: str, timeout_seconds: int) -> str:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = mirroring_status(client, workspace_id, mirror_id)
        if status != "Initializing":
            return status
        time.sleep(5)
    raise TimeoutError(f"Mirrored database {mirror_id} did not leave Initializing within {timeout_seconds} seconds.")


def wait_for_running_status(client: FabricClient, workspace_id: str, mirror_id: str, timeout_seconds: int) -> str:
    deadline = time.monotonic() + timeout_seconds
    status = mirroring_status(client, workspace_id, mirror_id)
    while time.monotonic() < deadline:
        if status == "Running":
            return status
        if status in {"Paused", "Stopped"}:
            raise RuntimeError(f"Mirrored database reached {status} instead of Running.")
        time.sleep(5)
        status = mirroring_status(client, workspace_id, mirror_id)
    raise TimeoutError(f"Mirrored database {mirror_id} did not reach Running within {timeout_seconds} seconds.")


def wait_for_sql_endpoint(
    client: FabricClient,
    workspace_id: str,
    mirror_id: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        endpoint = get_sql_endpoint_properties(client, workspace_id, mirror_id)
        if endpoint.get("id") and endpoint.get("connectionString"):
            return endpoint
        time.sleep(10)
    raise TimeoutError(f"Mirrored database {mirror_id} did not provision a SQL analytics endpoint within {timeout_seconds} seconds.")


def add_workspace_role(client: FabricClient, workspace_id: str, principal_id: str, role: str) -> None:
    try:
        client.request(
            "POST",
            f"/workspaces/{workspace_id}/roleAssignments",
            {
                "principal": {"id": principal_id, "type": "ServicePrincipal"},
                "role": role,
            },
        )
    except FabricApiError as exc:
        if exc.status != 409:
            raise


def write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(f"export {name}={json.dumps(value)}\n" for name, value in values.items() if value)
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-connection", action="store_true", default=env_bool("FABRIC_CREATE_CONNECTION"))
    parser.add_argument(
        "--grant-server-mi-workspace-role",
        action="store_true",
        default=env_bool("FABRIC_GRANT_AZURE_SQL_SERVER_MI_WORKSPACE_CONTRIBUTOR"),
        help="Grant the Azure SQL server identity Fabric workspace Contributor. This is broader than item-level permission.",
    )
    parser.add_argument(
        "--wait-for-running-seconds",
        type=int,
        default=int(os.environ.get("FABRIC_MIRROR_WAIT_FOR_RUNNING_SECONDS", "0")),
    )
    parser.add_argument(
        "--sql-endpoint-timeout-seconds",
        type=int,
        default=int(os.environ.get("FABRIC_SQL_ENDPOINT_PROVISION_TIMEOUT_SECONDS", "900")),
    )
    parser.add_argument(
        "--output",
        default=os.environ.get("FABRIC_SETUP_OUTPUT", "results/fabric-mirror-setup.json"),
    )
    parser.add_argument(
        "--env-output",
        default=os.environ.get("FABRIC_SETUP_ENV_OUTPUT", "results/fabric-mirror-setup.env"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace_name = env("FABRIC_WORKSPACE_NAME", "fpmb-benchmark")
    client = FabricClient(access_token())
    capacity_id = resolve_capacity_id(client, env("FABRIC_CAPACITY_ID"))

    workspace = find_workspace(client, workspace_name)
    if workspace is None:
        workspace = client.request(
            "POST",
            "/workspaces",
            {
                "displayName": workspace_name,
                "description": "Fabric mirroring benchmark workspace",
                "capacityId": capacity_id,
            },
        ).body
    workspace_id = workspace["id"]

    source_type = os.environ.get("SOURCE_TYPE", "postgresql")
    result: dict[str, Any] = {
        "capturedAt": utc_now(),
        "workspace": workspace,
        "sourceType": source_type,
    }
    if source_type != "azure-sql-db":
        result["nextStep"] = (
            "Azure SQL Database REST mirroring automation requires SOURCE_TYPE=azure-sql-db. "
            "Use the source adapter instructions for other source types."
        )
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0

    connection_id = optional_env("FABRIC_CONNECTION_ID")
    if not connection_id:
        if not args.create_connection:
            raise SystemExit(
                "Set FABRIC_CONNECTION_ID to an existing approved connection, or set "
                "FABRIC_CREATE_CONNECTION=true after configuring the FABRIC_SOURCE_* credentials."
            )
        connection = find_connection(
            client,
            env("FABRIC_CONNECTION_DISPLAY_NAME", "azure-sql-mirroring"),
            env("AZURE_SQL_HOST"),
            env("AZURE_SQL_DATABASE"),
        )
        reused_connection = connection is not None
        if connection is None:
            connection = client.request("POST", "/connections", build_connection_request()).body
        connection_id = connection["id"]
        result["connection"] = {**connection, "reused": reused_connection}
    else:
        result["connection"] = {"id": connection_id, "reused": True}

    mirror_name = env("FABRIC_MIRRORED_DATABASE_NAME", "tprocc-mirror")
    mirror = find_mirror(client, workspace_id, mirror_name)
    if mirror is None:
        definition = build_mirroring_definition(
            connection_id,
            env("FABRIC_MIRROR_DEFAULT_SCHEMA", "dbo"),
            parse_tables(optional_env("FABRIC_MIRROR_TABLES")),
        )
        encoded_definition = base64.b64encode(json.dumps(definition, separators=(",", ":")).encode("utf-8")).decode("ascii")
        mirror = client.request(
            "POST",
            f"/workspaces/{workspace_id}/mirroredDatabases",
            {
                "displayName": mirror_name,
                "description": "Azure SQL Database TPROC-C Fabric mirroring benchmark",
                "definition": {
                    "parts": [
                        {
                            "path": "mirroring.json",
                            "payload": encoded_definition,
                            "payloadType": "InlineBase64",
                        }
                    ]
                },
            },
        ).body
    mirror_id = mirror["id"]
    result["mirroredDatabase"] = mirror

    if args.grant_server_mi_workspace_role:
        add_workspace_role(client, workspace_id, env("AZURE_SQL_SERVER_PRINCIPAL_ID"), "Contributor")
        result["azureSqlServerIdentityWorkspaceRole"] = "Contributor"
    if env_bool("FABRIC_GRANT_BENCHMARK_VM_WORKSPACE_VIEWER"):
        add_workspace_role(client, workspace_id, env("AZURE_SQL_MSI_OBJECT_ID"), "Viewer")
        result["benchmarkVmIdentityWorkspaceRole"] = "Viewer"

    status = wait_for_startable_status(client, workspace_id, mirror_id, args.sql_endpoint_timeout_seconds)
    if status not in {"Running", "Starting"}:
        client.request(
            "POST",
            f"/workspaces/{workspace_id}/mirroredDatabases/{mirror_id}/startMirroring",
            {},
        )
        status = "Starting"

    if args.wait_for_running_seconds:
        status = wait_for_running_status(client, workspace_id, mirror_id, args.wait_for_running_seconds)
    result["mirroringStatus"] = status

    endpoint = wait_for_sql_endpoint(client, workspace_id, mirror_id, args.sql_endpoint_timeout_seconds)
    result["sqlAnalyticsEndpoint"] = endpoint
    connection_string = endpoint["connectionString"]
    sqlcmd_args = sqlcmd_args_from_connection_string(
        connection_string,
        optional_env("FABRIC_SQL_ANALYTICS_DATABASE") or mirror_name,
    )
    result["fabricSqlcmdArgs"] = sqlcmd_args

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_env_file(
        Path(args.env_output),
        {
            "FABRIC_WORKSPACE_ID": workspace_id,
            "FABRIC_MIRRORED_DATABASE_ID": mirror_id,
            "FABRIC_CONNECTION_ID": connection_id,
            "FABRIC_SQL_ANALYTICS_ENDPOINT_ID": str(endpoint["id"]),
            "FABRIC_SQL_ANALYTICS_ENDPOINT_CONNECTION_STRING": connection_string,
            "FABRIC_SQL_ANALYTICS_DATABASE": optional_env("FABRIC_SQL_ANALYTICS_DATABASE") or mirror_name,
            "FABRIC_SQLCMD_ARGS": sqlcmd_args or "",
        },
    )
    print(json.dumps(result, indent=2))
    print(f"Source {args.env_output} to use the generated non-secret Fabric settings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
