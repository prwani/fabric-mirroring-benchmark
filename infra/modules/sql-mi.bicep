param projectName string
param location string
param tags object
param token string
param entraAdminLogin string
param entraAdminObjectId string
param subnetId string

var managedInstanceName = 'mi-${projectName}-${token}'

resource managedInstance 'Microsoft.Sql/managedInstances@2023-08-01' = {
  name: managedInstanceName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'GP_Gen5'
    tier: 'GeneralPurpose'
    family: 'Gen5'
    capacity: 4
  }
  properties: {
    subnetId: subnetId
    storageSizeInGB: 32
    vCores: 4
    publicDataEndpointEnabled: true
    minimalTlsVersion: '1.2'
    administrators: {
      administratorType: 'ActiveDirectory'
      principalType: 'User'
      login: entraAdminLogin
      sid: entraAdminObjectId
      tenantId: tenant().tenantId
      azureADOnlyAuthentication: true
    }
  }
}

output managedInstanceName string = managedInstance.name
output principalId string = managedInstance.identity.principalId

