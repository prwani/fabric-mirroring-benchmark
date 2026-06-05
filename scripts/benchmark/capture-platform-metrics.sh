#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

load_env
require_env AZURE_RESOURCE_GROUP
require_env POSTGRES_SERVER_NAME

OUT="${1:-results/platform-metrics-$(date -u +%Y%m%dT%H%M%SZ).json}"
mkdir -p "$(dirname "$OUT")"

az monitor metrics list \
  --resource "/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourceGroups/${AZURE_RESOURCE_GROUP}/providers/Microsoft.DBforPostgreSQL/flexibleServers/${POSTGRES_SERVER_NAME}" \
  --metric cpu_percent,memory_percent,storage_percent,connections_failed,connections_succeeded,network_bytes_egress,network_bytes_ingress \
  --interval PT1M \
  --output json > "$OUT"

echo "Wrote Azure PostgreSQL platform metrics to $OUT"
echo "Capture Fabric mirroring status/latency from Fabric Monitoring UI/API separately when available; marker results remain the benchmark source of truth."

