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
  network: 'private'
}

@description('Benchmark VM admin username.')
param adminUsername string = 'azureuser'

@description('SSH public key for benchmark VM access. Generate one with ssh-keygen and paste the .pub file content.')
param adminSshPublicKey string

@description('Current client IP address in CIDR form, allowed to SSH to the benchmark VM, e.g. 203.0.113.10/32. Find it with curl -4 ifconfig.me or https://whatismyipaddress.com/.')
param currentClientIpAddress string

@description('Entra administrator login name for the Azure SQL logical server. Defaults to the signed-in deploying user for portal deployments.')
param sqlEntraAdminLogin string = deployer().userPrincipalName

@description('Entra administrator object ID for the Azure SQL logical server. Defaults to the deploying principal object ID.')
param sqlEntraAdminObjectId string = deployer().objectId

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
param azureSqlSkuName string = 'GP_Gen5_4'

@description('Azure SQL Database SKU tier.')
param azureSqlSkuTier string = 'GeneralPurpose'

@description('Azure SQL Database SKU family.')
param azureSqlSkuFamily string = 'Gen5'

@description('Azure SQL Database vCore capacity.')
param azureSqlSkuCapacity int = 4

@description('Azure SQL Database maximum size in bytes. Defaults to 32 GiB.')
param azureSqlMaxSizeBytes int = 34359738368

@description('Fabric capacity SKU for the benchmark.')
@allowed(['F2', 'F4', 'F8', 'F16', 'F32', 'F64'])
param fabricCapacitySku string = 'F8'

@description('UPN of the Fabric capacity administrator. Defaults to the signed-in deploying user for portal deployments.')
param fabricAdminUpn string = deployer().userPrincipalName

var token = toLower(uniqueString(subscription().id, resourceGroup().id, projectName, location))

module network 'modules/networking.bicep' = {
  name: 'network-${token}'
  params: {
    projectName: projectName
    location: location
    tags: tags
    currentClientIpAddress: currentClientIpAddress
    includePrivateSqlSubnet: true
    includeGatewaySubnet: true
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
    allowedBenchmarkIp: ''
    enablePublicNetworkAccess: false
    createPublicFirewallRules: false
    skuName: azureSqlSkuName
    skuTier: azureSqlSkuTier
    skuFamily: azureSqlSkuFamily
    skuCapacity: azureSqlSkuCapacity
    maxSizeBytes: azureSqlMaxSizeBytes
  }
}

module privateEndpoint 'modules/azure-sql-private-endpoint.bicep' = {
  name: 'azure-sql-private-endpoint-${token}'
  params: {
    projectName: projectName
    location: location
    tags: tags
    token: token
    sqlServerId: resourceId('Microsoft.Sql/servers', azureSqlDb.outputs.serverName)
    virtualNetworkId: network.outputs.virtualNetworkId
    privateEndpointSubnetId: network.outputs.privateSqlSubnetId
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
output fabricGatewaySubnetId string = network.outputs.gatewaySubnetId
output privateEndpointId string = privateEndpoint.outputs.privateEndpointId
output privateDnsZoneName string = privateEndpoint.outputs.privateDnsZoneName
output logAnalyticsWorkspaceId string = monitoring.outputs.workspaceId
