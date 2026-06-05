targetScope = 'resourceGroup'

@description('Short project prefix used in resource names.')
@minLength(2)
@maxLength(10)
param projectName string = 'fpmb'

@description('Azure region. Defaults to Sweden Central but is configurable for other regions.')
param location string = 'swedencentral'

@description('Tags applied to all resources.')
param tags object = {
  workload: 'fabric-postgres-mirroring-benchmark'
}

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

module postgres 'modules/postgres.bicep' = {
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

output postgresServerName string = postgres.outputs.serverName
output postgresFullyQualifiedDomainName string = postgres.outputs.fullyQualifiedDomainName
output benchmarkVmName string = vm.outputs.vmName
output benchmarkVmPublicIp string = vm.outputs.publicIpAddress
output fabricCapacityId string = fabric.outputs.capacityId
output fabricCapacityName string = fabric.outputs.capacityName
output logAnalyticsWorkspaceId string = monitoring.outputs.workspaceId
