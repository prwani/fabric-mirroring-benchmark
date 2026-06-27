param projectName string
param location string
param tags object
param token string
param adminUser string
@secure()
param adminPassword string
param databaseName string = 'tpch'
@allowed(['14', '15', '16'])
param version string = '16'
param skuName string = 'Standard_D2ds_v5'
@allowed(['GeneralPurpose', 'MemoryOptimized'])
param skuTier string = 'GeneralPurpose'
@minValue(32)
param storageGb int = 128
param allowedBenchmarkIp string
param enableMicrosoftEntraAuth bool = true
param entraAdminName string = ''
param entraAdminObjectId string = ''
@allowed([
  'Group'
  'ServicePrincipal'
  'User'
])
param entraAdminPrincipalType string = 'User'

var serverName = 'psql-${projectName}-${token}'

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: serverName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: version
    administratorLogin: adminUser
    administratorLoginPassword: adminPassword
    storage: {
      storageSizeGB: storageGb
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    authConfig: {
      activeDirectoryAuth: enableMicrosoftEntraAuth ? 'Enabled' : 'Disabled'
      passwordAuth: 'Enabled'
      tenantId: tenant().tenantId
    }
  }
}

resource entraAdministrator 'Microsoft.DBforPostgreSQL/flexibleServers/administrators@2024-08-01' = if (enableMicrosoftEntraAuth && !empty(entraAdminName) && !empty(entraAdminObjectId)) {
  parent: server
  name: entraAdminObjectId
  properties: {
    principalName: entraAdminName
    principalType: entraAdminPrincipalType
    tenantId: tenant().tenantId
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: server
  name: databaseName
  dependsOn: [
    azureExtensions
  ]
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource allowAzureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: server
  name: 'AllowAzureServices'
  dependsOn: [
    database
  ]
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource allowBenchmarkVm 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: server
  name: 'AllowBenchmarkVm'
  dependsOn: [
    allowAzureServices
  ]
  properties: {
    startIpAddress: allowedBenchmarkIp
    endIpAddress: allowedBenchmarkIp
  }
}

resource walLevel 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: server
  name: 'wal_level'
  properties: {
    value: 'logical'
    source: 'user-override'
  }
}

resource maxReplicationSlots 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: server
  name: 'max_replication_slots'
  dependsOn: [
    walLevel
  ]
  properties: {
    value: '20'
    source: 'user-override'
  }
}

resource maxWalSenders 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: server
  name: 'max_wal_senders'
  dependsOn: [
    maxReplicationSlots
  ]
  properties: {
    value: '20'
    source: 'user-override'
  }
}

resource azureExtensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: server
  name: 'azure.extensions'
  dependsOn: [
    maxWalSenders
  ]
  properties: {
    value: 'uuid-ossp,pg_stat_statements'
    source: 'user-override'
  }
}

output serverName string = server.name
output fullyQualifiedDomainName string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
output principalId string = server.identity.principalId
