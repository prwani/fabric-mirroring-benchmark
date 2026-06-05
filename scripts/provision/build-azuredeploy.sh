#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

ROOT="$(repo_root)"

az bicep build \
  --file "$ROOT/infra/main.bicep" \
  --outfile "$ROOT/azuredeploy.json"

echo "Wrote $ROOT/azuredeploy.json"

