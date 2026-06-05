targetScope = 'resourceGroup'

@description('Short project prefix used in resource names.')
@minLength(2)
@maxLength(10)
param projectName string = 'fpmb'

@description('Azure region. Defaults to Sweden Central but is configurable for other regions.')
param location string = 'swedencentral'

@description('Tags applied to all resources.')
param tags object = {
  workload: 'fabric-mirroring-benchmark'
}

@description('Source database type to provision for the benchmark. PostgreSQL is the validated default.')
@allowed([
  'postgresql'
  'mysql'
  'azure-sql-db'
  'sql-mi'
  'sql-server'
])
param sourceType string = 'postgresql'

@description('Benchmark VM admin username.')
param adminUsername string = 'azureuser'

@description('SSH public key for benchmark VM access.')
param adminSshPublicKey string

@description('Operator public IP CIDR allowed to SSH to the benchmark VM, e.g. 203.0.113.10/32.')
param operatorPublicIp string

@description('PostgreSQL administrator username.')
param postgresAdminUser string = 'pgadmin'

@secure()
@description('PostgreSQL administrator password.')
param postgresAdminPassword string

@description('PostgreSQL benchmark database name.')
param postgresDatabaseName string = 'tpch'

@description('PostgreSQL major version. Fabric mirroring requires PostgreSQL 14 or later.')
@allowed(['14', '15', '16'])
param postgresVersion string = '16'

@description('PostgreSQL non-burstable SKU name.')
param postgresSkuName string = 'Standard_D2ds_v5'

@description('PostgreSQL tier. Burstable is intentionally not allowed for Fabric mirroring.')
@allowed(['GeneralPurpose', 'MemoryOptimized'])
param postgresSkuTier string = 'GeneralPurpose'

@description('PostgreSQL storage size in GiB.')
@minValue(32)
param postgresStorageGb int = 128

@description('MySQL administrator username. Used when sourceType=mysql.')
param mysqlAdminUser string = 'mysqladmin'

@secure()
@description('MySQL administrator password. Used when sourceType=mysql.')
param mysqlAdminPassword string = ''

@description('MySQL benchmark database name. Used when sourceType=mysql.')
param mysqlDatabaseName string = 'tpch'

@description('MySQL Flexible Server version. Used when sourceType=mysql.')
param mysqlVersion string = '8.0.21'

@description('MySQL non-burstable SKU name. Used when sourceType=mysql.')
param mysqlSkuName string = 'Standard_D2ds_v4'

@description('MySQL storage size in GiB. Used when sourceType=mysql.')
@minValue(32)
param mysqlStorageGb int = 128

@description('Entra administrator login name for Azure SQL sources. Required when sourceType=azure-sql-db or sql-mi.')
param sqlEntraAdminLogin string = ''

@description('Entra administrator object ID for Azure SQL sources. Required when sourceType=azure-sql-db or sql-mi.')
param sqlEntraAdminObjectId string = ''

@description('Azure SQL Database name. Used when sourceType=azure-sql-db.')
param azureSqlDatabaseName string = 'tpch'

@description('SQL Server VM administrator username. Used when sourceType=sql-server.')
param sqlServerVmAdminUsername string = 'azureuser'

@secure()
@description('SQL Server VM administrator password. Used when sourceType=sql-server.')
param sqlServerVmAdminPassword string = ''

@description('Fabric capacity SKU for the benchmark.')
@allowed(['F2', 'F4', 'F8', 'F16', 'F32', 'F64'])
param fabricCapacitySku string = 'F8'

@description('UPN of the Fabric capacity administrator.')
param fabricAdminUpn string

var token = toLower(uniqueString(subscription().id, resourceGroup().id, projectName, location))

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

module postgres 'modules/postgres.bicep' = if (sourceType == 'postgresql') {
  name: 'postgres-${token}'
  params: {
    projectName: projectName
    location: location
    tags: tags
    token: token
    adminUser: postgresAdminUser
    adminPassword: postgresAdminPassword
    databaseName: postgresDatabaseName
    version: postgresVersion
    skuName: postgresSkuName
    skuTier: postgresSkuTier
    storageGb: postgresStorageGb
    allowedBenchmarkIp: network.outputs.publicIpAddress
  }
}

module mysql 'modules/mysql-flexible.bicep' = if (sourceType == 'mysql') {
  name: 'mysql-${token}'
  params: {
    projectName: projectName
    location: location
    tags: tags
    token: token
    adminUser: mysqlAdminUser
    adminPassword: mysqlAdminPassword
    databaseName: mysqlDatabaseName
    version: mysqlVersion
    skuName: mysqlSkuName
    storageGb: mysqlStorageGb
    allowedBenchmarkIp: network.outputs.publicIpAddress
  }
}

module azureSqlDb 'modules/azure-sql-db.bicep' = if (sourceType == 'azure-sql-db') {
  name: 'azure-sql-db-${token}'
  params: {
    projectName: projectName
    location: location
    tags: tags
    token: token
    databaseName: azureSqlDatabaseName
    entraAdminLogin: sqlEntraAdminLogin
    entraAdminObjectId: sqlEntraAdminObjectId
    allowedBenchmarkIp: network.outputs.publicIpAddress
  }
}

module sqlMi 'modules/sql-mi.bicep' = if (sourceType == 'sql-mi') {
  name: 'sql-mi-${token}'
  params: {
    projectName: projectName
    location: location
    tags: tags
    token: token
    entraAdminLogin: sqlEntraAdminLogin
    entraAdminObjectId: sqlEntraAdminObjectId
    subnetId: network.outputs.sqlMiSubnetId
  }
}

module sqlServer 'modules/sql-server-vm.bicep' = if (sourceType == 'sql-server') {
  name: 'sql-server-${token}'
  params: {
    projectName: projectName
    location: location
    tags: tags
    token: token
    adminUsername: sqlServerVmAdminUsername
    adminPassword: sqlServerVmAdminPassword
    subnetId: network.outputs.vmSubnetId
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

output sourceType string = sourceType
output postgresServerName string = sourceType == 'postgresql' ? postgres!.outputs.serverName : ''
output postgresFullyQualifiedDomainName string = sourceType == 'postgresql' ? postgres!.outputs.fullyQualifiedDomainName : ''
output mysqlServerName string = sourceType == 'mysql' ? mysql!.outputs.serverName : ''
output mysqlFullyQualifiedDomainName string = sourceType == 'mysql' ? mysql!.outputs.fullyQualifiedDomainName : ''
output azureSqlServerName string = sourceType == 'azure-sql-db' ? azureSqlDb!.outputs.serverName : ''
output azureSqlFullyQualifiedDomainName string = sourceType == 'azure-sql-db' ? azureSqlDb!.outputs.fullyQualifiedDomainName : ''
output azureSqlDatabaseName string = sourceType == 'azure-sql-db' ? azureSqlDb!.outputs.databaseName : ''
output sqlMiName string = sourceType == 'sql-mi' ? sqlMi!.outputs.managedInstanceName : ''
output sqlServerVmName string = sourceType == 'sql-server' ? sqlServer!.outputs.vmName : ''
output benchmarkVmName string = vm.outputs.vmName
output benchmarkVmPublicIp string = vm.outputs.publicIpAddress
output fabricCapacityId string = fabric.outputs.capacityId
output fabricCapacityName string = fabric.outputs.capacityName
output logAnalyticsWorkspaceId string = monitoring.outputs.workspaceId
