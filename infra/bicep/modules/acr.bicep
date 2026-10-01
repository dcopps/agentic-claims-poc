// Azure Container Registry (Phase 9.1).
//
// Basic SKU: one small image, built in-registry by `az acr build`. The admin
// user stays disabled — the Container App pulls with its managed identity via
// the AcrPull grant below, so no registry credential exists to copy anywhere.

@description('Registry name: 5–50 alphanumeric characters, globally unique.')
@minLength(5)
@maxLength(50)
param name string

@description('Azure region.')
param location string

@description('Principal id of the managed identity that pulls images.')
param pullPrincipalId string

// Built-in role: AcrPull.
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

// Deterministic assignment name so redeploys are no-ops rather than conflicts.
resource pullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, pullPrincipalId, acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: pullPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output name string = registry.name
output loginServer string = registry.properties.loginServer
