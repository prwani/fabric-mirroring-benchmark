#!/usr/bin/env bash
set -euo pipefail

HAMMERDB_VERSION="${HAMMERDB_VERSION:-5.0}"
INSTALL_DIR="${HAMMERDB_INSTALL_DIR:-$HOME/hammerdb}"

sudo apt-get update
sudo apt-get install -y curl jq unzip python3 python3-venv python3-pip postgresql-client tcl ca-certificates

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo "Install HammerDB $HAMMERDB_VERSION manually from https://www.hammerdb.com/download.html if no Linux archive URL is available for your selected version."
echo "Place hammerdbcli under $INSTALL_DIR/HammerDB-$HAMMERDB_VERSION/hammerdbcli or set HAMMERDB_CLI."

