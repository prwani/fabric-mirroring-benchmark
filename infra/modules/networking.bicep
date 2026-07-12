param projectName string
param location string
param tags object
param token string
param currentClientIpAddress string
param includePrivateSqlSubnet bool = false
param includeGatewaySubnet bool = false

var vnetName = 'vnet-${projectName}-${token}'
var nsgName = 'nsg-${projectName}-${token}'
var publicIpName = 'pip-${projectName}-${token}'
var vmSubnetName = 'snet-vm'
var sqlMiSubnetName = 'snet-sqlmi'
var privateSqlSubnetName = 'snet-private-endpoint'
var gatewaySubnetName = 'snet-fabric-gateway'

resource nsg 'Microsoft.Network/networkSecurityGroups@2024-07-01' = {
  name: nsgName
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowSshFromCurrentClient'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '22'
          sourceAddressPrefix: currentClientIpAddress
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource publicIp 'Microsoft.Network/publicIPAddresses@2024-07-01' = {
  name: publicIpName
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-07-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.42.0.0/16'
      ]
    }
    subnets: concat([
      {
        name: vmSubnetName
        properties: {
          addressPrefix: '10.42.1.0/24'
          networkSecurityGroup: {
            id: nsg.id
          }
        }
      }
      {
        name: sqlMiSubnetName
        properties: {
          addressPrefix: '10.42.2.0/24'
          delegations: [
            {
              name: 'managedInstanceDelegation'
              properties: {
                serviceName: 'Microsoft.Sql/managedInstances'
              }
            }
          ]
        }
      }
    ], includePrivateSqlSubnet ? [
      {
        name: privateSqlSubnetName
        properties: {
          addressPrefix: '10.42.3.0/27'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ] : [], includeGatewaySubnet ? [
      {
        name: gatewaySubnetName
        properties: {
          addressPrefix: '10.42.4.0/26'
          serviceEndpoints: [
            {
              service: 'Microsoft.Storage'
            }
          ]
          delegations: [
            {
              name: 'powerPlatformGatewayDelegation'
              properties: {
                serviceName: 'Microsoft.PowerPlatform/vnetaccesslinks'
              }
            }
          ]
        }
      }
    ] : [])
  }
}

output vmSubnetId string = vnet.properties.subnets[0].id
output sqlMiSubnetId string = vnet.properties.subnets[1].id
output privateSqlSubnetId string = includePrivateSqlSubnet ? vnet.properties.subnets[2].id : ''
output gatewaySubnetId string = includeGatewaySubnet && includePrivateSqlSubnet ? vnet.properties.subnets[3].id : ''
output virtualNetworkId string = vnet.id
output publicIpId string = publicIp.id
output publicIpName string = publicIp.name
output publicIpAddress string = publicIp.properties.ipAddress
