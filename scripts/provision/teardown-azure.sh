#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

load_env
require_env AZURE_SUBSCRIPTION_ID

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-fabric-pg-mirror-bench}"

cat <<'WARNING'
Before deleting Azure resources:
1. Stop/delete the Fabric mirrored database item.
2. Verify PostgreSQL replication slots are gone, or drop orphaned slots explicitly.
3. Export any result files you need from the benchmark VM.
WARNING

read -r -p "Type the resource group name to delete it: " CONFIRM
if [[ "$CONFIRM" != "$RESOURCE_GROUP" ]]; then
  echo "Confirmation did not match; aborting."
  exit 1
fi

az account set --subscription "$AZURE_SUBSCRIPTION_ID"
az group delete --name "$RESOURCE_GROUP" --yes --no-wait
echo "Delete submitted for $RESOURCE_GROUP at $(timestamp_utc)."

