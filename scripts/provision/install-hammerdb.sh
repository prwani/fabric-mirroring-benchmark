#!/usr/bin/env bash
set -euo pipefail

HAMMERDB_VERSION="${HAMMERDB_VERSION:-5.0}"
HOME="${HOME:-/root}"
INSTALL_DIR="${HAMMERDB_INSTALL_DIR:-$HOME/hammerdb}"

sudo apt-get update
sudo apt-get install -y curl jq unzip python3 python3-venv python3-pip postgresql-client tcl ca-certificates gnupg apt-transport-https

if ! command -v sqlcmd >/dev/null 2>&1; then
  . /etc/os-release
  curl -fsSL "https://packages.microsoft.com/config/ubuntu/${VERSION_ID}/packages-microsoft-prod.deb" -o /tmp/packages-microsoft-prod.deb
  sudo dpkg -i /tmp/packages-microsoft-prod.deb
  sudo apt-get update
  sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18 mssql-tools18 unixodbc-dev
  echo 'export PATH="$PATH:/opt/mssql-tools18/bin"' >> "$HOME/.profile"
fi

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

if [[ -z "${HAMMERDB_DOWNLOAD_URL:-}" ]]; then
  . /etc/os-release
  case "${VERSION_ID}" in
    22.04)
      HAMMERDB_DOWNLOAD_URL="https://downloads.sourceforge.net/project/hammerdb.mirror/v${HAMMERDB_VERSION}/HammerDB-${HAMMERDB_VERSION}-Prod-Lin-UBU22.tar.gz"
      ;;
    24.04)
      HAMMERDB_DOWNLOAD_URL="https://downloads.sourceforge.net/project/hammerdb.mirror/v${HAMMERDB_VERSION}/HammerDB-${HAMMERDB_VERSION}-Prod-Lin-UBU24.tar.gz"
      ;;
    *)
      HAMMERDB_DOWNLOAD_URL=""
      ;;
  esac
fi

if [[ -n "$HAMMERDB_DOWNLOAD_URL" && ! -x "$INSTALL_DIR/HammerDB-${HAMMERDB_VERSION}/hammerdbcli" ]]; then
  curl -fL "$HAMMERDB_DOWNLOAD_URL" -o "HammerDB-${HAMMERDB_VERSION}.tar.gz"
  tar -xzf "HammerDB-${HAMMERDB_VERSION}.tar.gz"
fi

if [[ -x "$INSTALL_DIR/HammerDB-${HAMMERDB_VERSION}/hammerdbcli" ]]; then
  echo "export HAMMERDB_CLI=$INSTALL_DIR/HammerDB-${HAMMERDB_VERSION}/hammerdbcli" >> "$HOME/.profile"
  echo "HammerDB CLI installed at $INSTALL_DIR/HammerDB-${HAMMERDB_VERSION}/hammerdbcli"
else
  echo "Install HammerDB $HAMMERDB_VERSION manually from https://www.hammerdb.com/download.html if no Linux archive URL is available for your selected version."
  echo "Place hammerdbcli under $INSTALL_DIR/HammerDB-$HAMMERDB_VERSION/hammerdbcli or set HAMMERDB_CLI."
fi
