param projectName string
param location string
param tags object
param token string

@allowed(['F2', 'F4', 'F8', 'F16', 'F32', 'F64'])
param skuName string = 'F8'

param adminUpn string

resource capacity 'Microsoft.Fabric/capacities@2023-11-01' = {
  name: '${projectName}fab${token}'
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: 'Fabric'
  }
  properties: {
    administration: {
      members: [
        adminUpn
      ]
    }
  }
}

output capacityId string = capacity.id
output capacityName string = capacity.name
output capacitySku string = capacity.sku.name

