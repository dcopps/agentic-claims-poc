// Azure Container Registry (Phase 9.1).
//
// Basic SKU: one small image, built in-registry by `az acr build`. The admin
// user stays disabled — the Container App pulls with its managed identity via
// the AcrPull grant below, so no registry credential exists to copy anywhere.
//
// Phase 9.2 adds the deployer identity (GitHub Actions, OIDC) with two grants:
// AcrPush to push the built layers, and Container Registry Tasks Contributor
// because `az acr build` is an ACR Task run (scheduleRun, the source upload
// URL, run logs) — AcrPush alone cannot queue a build.

@description('Registry name: 5–50 alphanumeric characters, globally unique.')
@minLength(5)
@maxLength(50)
param name string

@description('Azure region.')
param location string

@description('Principal id of the managed identity that pulls images.')
param pullPrincipalId string

@description('Principal id of the deployer identity that builds and pushes images.')
param pushPrincipalId string

// Built-in roles.
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var acrPushRoleId = '8311e382-0749-4cb8-b61a-304f252e45ec'
var acrTasksContributorRoleId = 'fb382eab-e894-4461-af04-94435c366c3f'

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

resource pushAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, pushPrincipalId, acrPushRoleId)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPushRoleId)
    principalId: pushPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource tasksAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, pushPrincipalId, acrTasksContributorRoleId)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrTasksContributorRoleId)
    principalId: pushPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output name string = registry.name
output loginServer string = registry.properties.loginServer
