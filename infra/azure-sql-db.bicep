targetScope = 'resourceGroup'

@description('Short project prefix used in resource names.')
@minLength(2)
@maxLength(10)
param projectName string = 'fsqlmb'

@description('Azure region. Defaults to Sweden Central but is configurable for other regions.')
param location string = 'swedencentral'

@description('Tags applied to all resources.')
param tags object = {
  workload: 'fabric-mirroring-benchmark'
  source: 'azure-sql-db'
}

@description('Benchmark VM admin username.')
param adminUsername string = 'azureuser'

@description('SSH public key for benchmark VM access. Generate one with ssh-keygen and paste the .pub file content.')
param adminSshPublicKey string

@description('Operator public IP CIDR allowed to SSH to the benchmark VM, e.g. 203.0.113.10/32.')
param operatorPublicIp string

@description('Entra administrator login name for the Azure SQL logical server.')
param sqlEntraAdminLogin string

@description('Entra administrator object ID for the Azure SQL logical server.')
param sqlEntraAdminObjectId string

@description('Azure SQL Database name.')
param azureSqlDatabaseName string = 'tprocc'

@description('Azure SQL logical server SQL authentication administrator login. Used only when azureSqlAzureAdOnlyAuthentication is false.')
param azureSqlAdminUser string = 'sqladmin'

@secure()
@description('Azure SQL logical server SQL authentication administrator password. Leave empty when azureSqlAzureAdOnlyAuthentication is true.')
param azureSqlAdminPassword string = ''

@description('Require Microsoft Entra-only authentication for Azure SQL Database. Keep true for Entra-only tenants.')
param azureSqlAzureAdOnlyAuthentication bool = true

@description('Azure SQL Database SKU name.')
param azureSqlSkuName string = 'GP_Gen5_2'

@description('Azure SQL Database SKU tier.')
param azureSqlSkuTier string = 'GeneralPurpose'

@description('Azure SQL Database SKU family.')
param azureSqlSkuFamily string = 'Gen5'

@description('Azure SQL Database vCore capacity.')
param azureSqlSkuCapacity int = 2

@description('Azure SQL Database maximum size in bytes. Defaults to 32 GiB.')
param azureSqlMaxSizeBytes int = 34359738368

@description('Fabric capacity SKU for the benchmark.')
@allowed(['F2', 'F4', 'F8', 'F16', 'F32', 'F64'])
param fabricCapacitySku string = 'F8'

@description('UPN of the Fabric capacity administrator.')
param fabricAdminUpn string

var token = toLower(uniqueString(subscription().id, resourceGroup().id, projectName, location))
var operatorSqlFirewallIp = replace(operatorPublicIp, '/32', '')

module network 'modules/networking.bicep' = {
  name: 'network-${token}'
  params: {
    projectName: projectName
    location: location
    tags: tags
    operatorPublicIp: operatorPublicIp
    token: token
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring-${token}'
  params: {
    projectName: projectName
    location: location
    tags: tags
    token: token
  }
}

module azureSqlDb 'modules/azure-sql-db.bicep' = {
  name: 'azure-sql-db-${token}'
  params: {
    projectName: projectName
    location: location
    tags: tags
    token: token
    databaseName: azureSqlDatabaseName
    adminLogin: azureSqlAdminUser
    adminPassword: azureSqlAdminPassword
    entraAdminLogin: sqlEntraAdminLogin
    entraAdminObjectId: sqlEntraAdminObjectId
    azureAdOnlyAuthentication: azureSqlAzureAdOnlyAuthentication
    allowedBenchmarkIp: network.outputs.publicIpAddress
    allowedOperatorIp: operatorSqlFirewallIp
    skuName: azureSqlSkuName
    skuTier: azureSqlSkuTier
    skuFamily: azureSqlSkuFamily
    skuCapacity: azureSqlSkuCapacity
    maxSizeBytes: azureSqlMaxSizeBytes
  }
}

module vm 'modules/benchmark-vm.bicep' = {
  name: 'benchmark-vm-${token}'
  params: {
    projectName: projectName
    location: location
    tags: tags
    token: token
    adminUsername: adminUsername
    adminSshPublicKey: adminSshPublicKey
    subnetId: network.outputs.vmSubnetId
    publicIpId: network.outputs.publicIpId
    logAnalyticsWorkspaceId: monitoring.outputs.workspaceId
  }
}

module fabric 'modules/fabric-capacity.bicep' = {
  name: 'fabric-${token}'
  params: {
    projectName: projectName
    location: location
    tags: tags
    token: token
    skuName: fabricCapacitySku
    adminUpn: fabricAdminUpn
  }
}

output sourceType string = 'azure-sql-db'
output azureSqlServerName string = azureSqlDb.outputs.serverName
output azureSqlFullyQualifiedDomainName string = azureSqlDb.outputs.fullyQualifiedDomainName
output azureSqlDatabaseName string = azureSqlDb.outputs.databaseName
output azureSqlServerPrincipalId string = azureSqlDb.outputs.principalId
output benchmarkVmName string = vm.outputs.vmName
output benchmarkVmPublicIp string = vm.outputs.publicIpAddress
output fabricCapacityId string = fabric.outputs.capacityId
output fabricCapacityName string = fabric.outputs.capacityName
output logAnalyticsWorkspaceId string = monitoring.outputs.workspaceId
