#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

load_env

ROOT="$(repo_root)"
LOCATION="${AZURE_LOCATION:-swedencentral}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-fabric-pg-mirror-bench}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-fabric-pg-mirror-bench}"

require_env AZURE_SUBSCRIPTION_ID
require_env ADMIN_UPN
require_env CURRENT_CLIENT_IP_ADDRESS

SOURCE_TYPE="${SOURCE_TYPE:-postgresql}"
case "$SOURCE_TYPE" in
  postgresql)
    require_env POSTGRES_ADMIN_PASSWORD
    ;;
  mysql)
    require_env MYSQL_ADMIN_PASSWORD
    ;;
  azure-sql-db)
    require_env SQL_ENTRA_ADMIN_LOGIN
    require_env SQL_ENTRA_ADMIN_OBJECT_ID
    if [[ "${AZURE_SQL_AAD_ONLY_AUTH:-true}" != "true" ]]; then
      require_env AZURE_SQL_ADMIN_PASSWORD
    fi
    ;;
  sql-mi | sql-server)
    ;;
  *)
    echo "Unsupported SOURCE_TYPE: $SOURCE_TYPE" >&2
    exit 1
    ;;
esac

az account set --subscription "$AZURE_SUBSCRIPTION_ID"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --only-show-errors >/dev/null

SSH_KEY="${ADMIN_SSH_PUBLIC_KEY:-}"
if [[ -z "$SSH_KEY" ]]; then
  SSH_KEY="$(cat "$HOME/.ssh/id_rsa.pub")"
fi

az deployment group create \
  --name "$DEPLOYMENT_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --template-file "$ROOT/infra/main.bicep" \
  --parameters \
    projectName="${PROJECT_NAME:-fpmb}" \
    sourceType="$SOURCE_TYPE" \
    location="$LOCATION" \
    adminSshPublicKey="$SSH_KEY" \
    currentClientIpAddress="$CURRENT_CLIENT_IP_ADDRESS" \
    postgresAdminUser="${POSTGRES_ADMIN_USER:-pgadmin}" \
    postgresAdminPassword="${POSTGRES_ADMIN_PASSWORD:-}" \
    postgresDatabaseName="${POSTGRES_DATABASE:-tprocc}" \
    postgresVersion="${POSTGRES_VERSION:-16}" \
    postgresSkuName="${POSTGRES_SKU_NAME:-Standard_D2ds_v5}" \
    postgresSkuTier="${POSTGRES_SKU_TIER:-GeneralPurpose}" \
    postgresStorageGb="${POSTGRES_STORAGE_GB:-128}" \
    postgresEnableMicrosoftEntraAuth="${POSTGRES_ENABLE_ENTRA_AUTH:-true}" \
    postgresEntraAdminName="${POSTGRES_ENTRA_ADMIN_NAME:-}" \
    postgresEntraAdminObjectId="${POSTGRES_ENTRA_ADMIN_OBJECT_ID:-}" \
    postgresEntraAdminPrincipalType="${POSTGRES_ENTRA_ADMIN_PRINCIPAL_TYPE:-User}" \
    mysqlAdminUser="${MYSQL_ADMIN_USER:-mysqladmin}" \
    mysqlAdminPassword="${MYSQL_ADMIN_PASSWORD:-}" \
    mysqlDatabaseName="${MYSQL_DATABASE:-tprocc}" \
    mysqlVersion="${MYSQL_VERSION:-8.0.21}" \
    mysqlSkuName="${MYSQL_SKU_NAME:-Standard_D2ds_v4}" \
    mysqlStorageGb="${MYSQL_STORAGE_GB:-128}" \
    sqlEntraAdminLogin="${SQL_ENTRA_ADMIN_LOGIN:-}" \
    sqlEntraAdminObjectId="${SQL_ENTRA_ADMIN_OBJECT_ID:-}" \
    azureSqlDatabaseName="${AZURE_SQL_DATABASE:-tprocc}" \
    azureSqlAdminUser="${AZURE_SQL_ADMIN_USER:-sqladmin}" \
    azureSqlAdminPassword="${AZURE_SQL_ADMIN_PASSWORD:-}" \
    azureSqlAzureAdOnlyAuthentication="${AZURE_SQL_AAD_ONLY_AUTH:-true}" \
    azureSqlSkuName="${AZURE_SQL_SKU_NAME:-GP_Gen5_4}" \
    azureSqlSkuTier="${AZURE_SQL_SKU_TIER:-GeneralPurpose}" \
    azureSqlSkuFamily="${AZURE_SQL_SKU_FAMILY:-Gen5}" \
    azureSqlSkuCapacity="${AZURE_SQL_SKU_CAPACITY:-4}" \
    azureSqlMaxSizeBytes="${AZURE_SQL_MAX_SIZE_BYTES:-34359738368}" \
    sqlServerVmAdminUsername="${SQL_SERVER_VM_ADMIN_USERNAME:-azureuser}" \
    sqlServerVmAdminPassword="${SQL_SERVER_VM_ADMIN_PASSWORD:-}" \
    fabricCapacitySku="${FABRIC_CAPACITY_SKU:-F8}" \
    fabricAdminUpn="$ADMIN_UPN" \
  --only-show-errors

echo "Deployment completed at $(timestamp_utc)."
