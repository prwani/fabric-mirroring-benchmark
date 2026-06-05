# Azure Deployment Plan

## 1. Status

Validated

## 2. Goal

Deploy and test the Azure infrastructure template used by the README "Deploy to Azure" button for the Fabric PostgreSQL Mirroring Benchmark project.

## 3. Recipe

Type: Bicep / ARM template via Azure CLI

Deployment command shape:

```bash
az deployment group create \
  --resource-group <resource-group> \
  --template-file azuredeploy.json \
  --parameters @<generated-parameters-file>
```

## 4. Target Azure Context

- Subscription name: `ME-M365CPI88726844-prafullawani-2`
- Default region: `swedencentral`
- Resource group: `rg-fabric-pg-mirror-bench-test`

## 5. Resources

- Azure Database for PostgreSQL Flexible Server
- Linux benchmark VM
- Microsoft Fabric capacity
- Virtual network, subnet, NSG, public IP, NIC
- Log Analytics workspace

## 6. Validation Checklist

- Build Bicep to root `azuredeploy.json`.
- Validate generated ARM template syntax.
- Confirm Azure subscription context.
- Confirm resource group can be created in Sweden Central.
- Run ARM template validation before live deployment.
- Deploy through the same root `azuredeploy.json` used by the Deploy to Azure button.
- Verify deployment outputs and resource provisioning state.

## 7. Validation Proof

- `az account show` confirmed subscription `ME-M365CPI88726844-prafullawani-2` (`23835f6b-9ad7-4c33-b0b8-55157ad0d2b5`) as `admin@M365CPI88726844.onmicrosoft.com`.
- `az bicep build --file infra/main.bicep --outfile azuredeploy.json` completed successfully.
- `az group create --name rg-fabric-pg-mirror-bench-test --location swedencentral` completed successfully.
- `az deployment group validate --resource-group rg-fabric-pg-mirror-bench-test --template-file azuredeploy.json --parameters @<session>/fpmb-deploy.parameters.json` completed successfully.

## 8. Deployment Proof

- `az deployment group create --name deploy-to-azure-button-test --resource-group rg-fabric-pg-mirror-bench-test --template-file azuredeploy.json --parameters @<session>/fpmb-deploy.parameters.json` completed successfully after fixing PostgreSQL configuration serialization and removing unsupported manual `azure_cdc` extension allow-listing.
- Deployment outputs:
  - PostgreSQL server: `psql-fpmb-gtp2yxsvlktrg.postgres.database.azure.com`
  - Benchmark VM: `vm-fpmb-gtp2yxsvlktrg`
  - Benchmark VM public IP: `4.225.163.76`
  - Fabric capacity: `fpmbfabgtp2yxsvlktrg`
  - Log Analytics workspace: `log-fpmb-gtp2yxsvlktrg`
- `az resource list -g rg-fabric-pg-mirror-bench-test` showed the expected PostgreSQL server, VM, Fabric capacity, networking, disk, extension, and Log Analytics resources in `swedencentral`.
- PostgreSQL verification showed:
  - State: `Ready`
  - Version: `16`
  - SKU: `Standard_D2ds_v5`
  - Tier: `GeneralPurpose`
  - Public network access: `Enabled`
  - `wal_level=logical`
  - `azure.extensions=uuid-ossp,pg_stat_statements`
