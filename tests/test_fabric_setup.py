"""Unit tests for the Azure SQL Database Fabric setup request builders."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = REPO_ROOT / "scripts/provision/setup-fabric-items.py"
SPEC = importlib.util.spec_from_file_location("setup_fabric_items", SETUP_SCRIPT)
assert SPEC and SPEC.loader
SETUP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SETUP
SPEC.loader.exec_module(SETUP)


class FabricSetupTests(unittest.TestCase):
    def test_selective_azure_sql_definition_uses_expected_schema(self) -> None:
        tables = SETUP.parse_tables("dbo.stock,dbo.fabric_cdc_latency_marker")

        definition = SETUP.build_mirroring_definition("connection-id", "dbo", tables)

        self.assertEqual(definition["properties"]["source"]["type"], "AzureSqlDatabase")
        self.assertEqual(
            definition["properties"]["source"]["typeProperties"]["connection"],
            "connection-id",
        )
        self.assertEqual(definition["properties"]["target"]["type"], "MountedRelationalDatabase")
        self.assertEqual(definition["properties"]["target"]["typeProperties"]["format"], "Delta")
        self.assertEqual(
            definition["properties"]["mountedTables"][1]["source"]["typeProperties"]["tableName"],
            "fabric_cdc_latency_marker",
        )

    def test_empty_table_selection_omits_mounted_tables(self) -> None:
        definition = SETUP.build_mirroring_definition("connection-id", "dbo", [])

        self.assertNotIn("mountedTables", definition["properties"])

    def test_connection_request_uses_key_vault_reference_without_secret(self) -> None:
        values = {
            "AZURE_SQL_HOST": "example.database.windows.net",
            "AZURE_SQL_DATABASE": "tprocc",
            "FABRIC_SOURCE_TENANT_ID": "tenant-id",
            "FABRIC_SOURCE_SERVICE_PRINCIPAL_CLIENT_ID": "client-id",
            "FABRIC_KEY_VAULT_CONNECTION_ID": "key-vault-connection-id",
            "FABRIC_KEY_VAULT_SECRET_NAME": "fabric-source-secret",
        }
        with patch.dict(os.environ, values, clear=True):
            request = SETUP.build_connection_request()

        credentials = request["credentialDetails"]["credentials"]
        self.assertEqual(credentials["credentialType"], "ServicePrincipal")
        self.assertNotIn("servicePrincipalSecret", credentials)
        self.assertEqual(
            credentials["servicePrincipalSecretReference"]["secretName"],
            "fabric-source-secret",
        )
        self.assertEqual(request["credentialDetails"]["connectionEncryption"], "Encrypted")

    def test_sqlcmd_arguments_are_derived_from_fabric_connection_string(self) -> None:
        args = SETUP.sqlcmd_args_from_connection_string(
            "Data Source=abc.datawarehouse.fabric.microsoft.com;Initial Catalog=tprocc_mirror;Encrypt=True;"
        )

        self.assertEqual(
            args,
            "-C -S abc.datawarehouse.fabric.microsoft.com -d tprocc_mirror -G",
        )

    def test_sqlcmd_arguments_use_mirror_name_for_hostname_response(self) -> None:
        args = SETUP.sqlcmd_args_from_connection_string(
            "abc.datawarehouse.fabric.microsoft.com",
            "tprocc-mirror",
        )

        self.assertEqual(
            args,
            "-C -S abc.datawarehouse.fabric.microsoft.com -d tprocc-mirror -G",
        )

    def test_connection_lookup_reuses_matching_sql_connection(self) -> None:
        class Client:
            def list_values(self, path: str) -> list[dict]:
                self.path = path
                return [
                    {
                        "id": "wrong-server",
                        "displayName": "mirror-source",
                        "connectionDetails": {"type": "SQL", "path": "other.database.windows.net;tprocc"},
                    },
                    {
                        "id": "matching-connection",
                        "displayName": "mirror-source",
                        "connectionDetails": {"type": "SQL", "path": "source.database.windows.net;tprocc"},
                    },
                ]

        client = Client()

        connection = SETUP.find_connection(
            client,
            "mirror-source",
            "source.database.windows.net",
            "tprocc",
        )

        self.assertEqual(client.path, "/connections")
        self.assertEqual(connection["id"], "matching-connection")


if __name__ == "__main__":
    unittest.main()
