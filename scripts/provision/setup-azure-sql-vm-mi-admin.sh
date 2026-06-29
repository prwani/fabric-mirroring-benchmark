#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

load_env

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-fabric-sqldb-mirror-bench}"
SQL_SERVER_NAME="${AZURE_SQL_SERVER_NAME:-}"
VM_NAME="${BENCHMARK_VM_NAME:-}"

require_env AZURE_SUBSCRIPTION_ID

if [[ -z "$SQL_SERVER_NAME" ]]; then
  echo "Missing required environment variable: AZURE_SQL_SERVER_NAME" >&2
  exit 1
fi

if [[ -z "$VM_NAME" ]]; then
  echo "Missing required environment variable: BENCHMARK_VM_NAME" >&2
  exit 1
fi

az account set --subscription "$AZURE_SUBSCRIPTION_ID"

VM_PRINCIPAL_ID="$(az vm identity show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VM_NAME" \
  --query principalId \
  -o tsv)"

if [[ -z "$VM_PRINCIPAL_ID" ]]; then
  echo "VM $VM_NAME does not have a system-assigned managed identity." >&2
  exit 1
fi

az sql server ad-admin create \
  --resource-group "$RESOURCE_GROUP" \
  --server "$SQL_SERVER_NAME" \
  --display-name "$VM_NAME" \
  --object-id "$VM_PRINCIPAL_ID" \
  --only-show-errors

echo "Configured $VM_NAME ($VM_PRINCIPAL_ID) as Microsoft Entra admin for $SQL_SERVER_NAME."
