param projectName string
param location string
param tags object
param token string
param databaseName string = 'tprocc'
param adminLogin string = 'sqladmin'
@secure()
param adminPassword string
param entraAdminLogin string = ''
param entraAdminObjectId string = ''
param azureAdOnlyAuthentication bool = true
param allowedBenchmarkIp string
param allowedOperatorIp string = ''
param enablePublicNetworkAccess bool = true
param createPublicFirewallRules bool = true
param skuName string = 'GP_Gen5_4'
param skuTier string = 'GeneralPurpose'
param skuFamily string = 'Gen5'
param skuCapacity int = 4
param maxSizeBytes int = 34359738368

var serverName = 'sql-${projectName}-${token}'
var enableEntraAdmin = !empty(entraAdminLogin) && !empty(entraAdminObjectId)
var enableSqlAdmin = !azureAdOnlyAuthentication

resource server 'Microsoft.Sql/servers@2023-08-01' = {
  name: serverName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: union(union({
    publicNetworkAccess: enablePublicNetworkAccess ? 'Enabled' : 'Disabled'
    minimalTlsVersion: '1.2'
  }, enableSqlAdmin ? {
    administratorLogin: adminLogin
    administratorLoginPassword: adminPassword
  } : {}), enableEntraAdmin ? {
    administrators: {
      administratorType: 'ActiveDirectory'
      principalType: 'User'
      login: entraAdminLogin
      sid: entraAdminObjectId
      tenantId: tenant().tenantId
      azureADOnlyAuthentication: azureAdOnlyAuthentication
    }
  } : {})
}

resource allowAzureServices 'Microsoft.Sql/servers/firewallRules@2023-08-01' = if (createPublicFirewallRules) {
  parent: server
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource allowBenchmarkVm 'Microsoft.Sql/servers/firewallRules@2023-08-01' = if (createPublicFirewallRules) {
  parent: server
  name: 'AllowBenchmarkVm'
  properties: {
    startIpAddress: allowedBenchmarkIp
    endIpAddress: allowedBenchmarkIp
  }
}

resource allowOperatorIp 'Microsoft.Sql/servers/firewallRules@2023-08-01' = if (createPublicFirewallRules && !empty(allowedOperatorIp)) {
  parent: server
  name: 'AllowOperatorIp'
  properties: {
    startIpAddress: allowedOperatorIp
    endIpAddress: allowedOperatorIp
  }
}

resource database 'Microsoft.Sql/servers/databases@2023-08-01' = {
  parent: server
  name: databaseName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
    family: skuFamily
    capacity: skuCapacity
  }
  properties: {
    maxSizeBytes: maxSizeBytes
    zoneRedundant: false
    readScale: 'Disabled'
    requestedBackupStorageRedundancy: 'Local'
  }
}

output serverName string = server.name
output fullyQualifiedDomainName string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
output principalId string = server.identity.principalId
