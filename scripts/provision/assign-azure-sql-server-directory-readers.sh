#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

load_env

require_env AZURE_SUBSCRIPTION_ID
require_env AZURE_RESOURCE_GROUP
require_env AZURE_SQL_SERVER_NAME

az account set --subscription "$AZURE_SUBSCRIPTION_ID"

principal_id="$(az sql server show \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$AZURE_SQL_SERVER_NAME" \
  --query 'identity.principalId' \
  -o tsv)"
if [[ -z "$principal_id" ]]; then
  echo "Azure SQL logical server $AZURE_SQL_SERVER_NAME does not have a system-assigned identity." >&2
  exit 1
fi

role_definition_id="88d8e3e3-8f55-4a1e-953a-9b9898b8876b"
filter="principalId eq '$principal_id' and roleDefinitionId eq '$role_definition_id' and directoryScopeId eq '/'"
assignments_url="https://graph.microsoft.com/v1.0/roleManagement/directory/roleAssignments?\$filter=${filter// /%20}"
existing_assignment_id="$(az rest \
  --method get \
  --url "$assignments_url" \
  --resource https://graph.microsoft.com \
  --query 'value[0].id' \
  -o tsv)"

if [[ -n "$existing_assignment_id" ]]; then
  echo "Directory Readers is already assigned to Azure SQL server identity $principal_id."
  exit 0
fi

payload="$(printf '{"principalId":"%s","roleDefinitionId":"%s","directoryScopeId":"/"}' "$principal_id" "$role_definition_id")"
az rest \
  --method post \
  --url "https://graph.microsoft.com/v1.0/roleManagement/directory/roleAssignments" \
  --resource https://graph.microsoft.com \
  --body "$payload" \
  --query '{assignmentId:id,principalId:principalId,roleDefinitionId:roleDefinitionId}' \
  -o json
