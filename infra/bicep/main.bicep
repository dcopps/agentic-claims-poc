// Azure foundation for the agentic-claims prototype (Phase 9.1).
//
// Resource-group scope. Wires six single-purpose modules in dependency order:
// identity → monitoring → postgres → registry → key vault → container apps.
// Secrets arrive as @secure() parameters supplied from the shell (see
// main.bicepparam) and land only in Key Vault. Bicep is the only way anything
// in the resource group is created, so `what-if` is a truthful preview and the
// deployment is reproducible.

targetScope = 'resourceGroup'

// Length limits are set so the Key Vault name (3 + prefix + 1 + env + 1 + 5)
// provably fits its 24-character maximum for every allowed input.
@description('Short prefix for every resource name.')
@minLength(3)
@maxLength(8)
param namePrefix string = 'claimsai'

@description('Environment suffix, e.g. dev.')
@minLength(2)
@maxLength(4)
param environmentName string = 'dev'

@description('Azure region. Defaults to the resource group location.')
param location string = resourceGroup().location

@description('PostgreSQL major version.')
param postgresVersion string = '17'

@description('Postgres compute SKU.')
param postgresSkuName string = 'Standard_B1ms'

@description('Postgres compute tier.')
param postgresTier string = 'Burstable'

@description('Postgres storage in GiB.')
param postgresStorageGiB int = 32

@description('Postgres administrator login.')
param postgresAdminLogin string = 'claimsadmin'

@description('Application database name.')
param postgresDatabaseName string = 'agentic_claims'

@secure()
@description('Postgres administrator password; generated at deploy time.')
param postgresAdminPassword string

@secure()
@description('Anthropic API key.')
param anthropicApiKey string

@secure()
@description('Mistral API key (used by the v1_mistral replay variant).')
param mistralApiKey string

@description('Public IPv4 of the deploying machine, for the Postgres firewall.')
param deployerClientIp string

@description('Entra object id of the deploying user, for Key Vault data-plane access.')
param deployerPrincipalId string

@description('Backend image reference. Empty on pass 1 (no Container App yet).')
param containerImage string = ''

@description('Container vCPU.')
param containerCpu string = '1.0'

@description('Container memory.')
param containerMemory string = '2Gi'

@description('Minimum replicas: 0 scales to zero between demos; 1 keeps one warm.')
@minValue(0)
param minReplicas int = 0

@description('Maximum replicas.')
@minValue(1)
param maxReplicas int = 1

@description('JSON list of allowed CORS origins.')
param corsAllowedOrigins string = '["https://agentic-claims-poc.vercel.app"]'

// Deterministic per resource group, so redeploys produce the same names.
var suffix = take(uniqueString(resourceGroup().id), 5)
var base = '${namePrefix}-${environmentName}'

var names = {
  identity: 'id-${base}-backend'
  logAnalytics: 'log-${base}'
  keyVault: 'kv-${base}-${suffix}'
  // Registry names allow alphanumerics only.
  registry: 'acr${namePrefix}${environmentName}${suffix}'
  postgres: 'psql-${base}-${suffix}'
  environment: 'cae-${base}'
  app: 'ca-${base}-backend'
}

module identity 'modules/identity.bicep' = {
  name: 'identity'
  params: {
    name: names.identity
    location: location
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    name: names.logAnalytics
    location: location
  }
}

module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  params: {
    name: names.postgres
    location: location
    version: postgresVersion
    skuName: postgresSkuName
    tier: postgresTier
    storageGiB: postgresStorageGiB
    adminLogin: postgresAdminLogin
    adminPassword: postgresAdminPassword
    databaseName: postgresDatabaseName
    deployerClientIp: deployerClientIp
  }
}

module registry 'modules/acr.bicep' = {
  name: 'registry'
  params: {
    name: names.registry
    location: location
    pullPrincipalId: identity.outputs.principalId
  }
}

module keyVault 'modules/keyvault.bicep' = {
  name: 'keyVault'
  params: {
    name: names.keyVault
    location: location
    appPrincipalId: identity.outputs.principalId
    deployerPrincipalId: deployerPrincipalId
    postgresFqdn: postgres.outputs.fqdn
    postgresDatabaseName: postgres.outputs.databaseName
    postgresAdminLogin: postgresAdminLogin
    postgresAdminPassword: postgresAdminPassword
    anthropicApiKey: anthropicApiKey
    mistralApiKey: mistralApiKey
  }
}

module containerApps 'modules/containerapps.bicep' = {
  name: 'containerApps'
  params: {
    environmentName: names.environment
    appName: names.app
    location: location
    logAnalyticsName: monitoring.outputs.name
    identityId: identity.outputs.id
    acrLoginServer: registry.outputs.loginServer
    containerImage: containerImage
    databaseUrlSecretUri: keyVault.outputs.databaseUrlSecretUri
    anthropicApiKeySecretUri: keyVault.outputs.anthropicApiKeySecretUri
    mistralApiKeySecretUri: keyVault.outputs.mistralApiKeySecretUri
    corsAllowedOrigins: corsAllowedOrigins
    cpu: containerCpu
    memory: containerMemory
    minReplicas: minReplicas
    maxReplicas: maxReplicas
  }
}

output registryName string = registry.outputs.name
output registryLoginServer string = registry.outputs.loginServer
output keyVaultName string = keyVault.outputs.name
output postgresServerName string = postgres.outputs.name
output postgresFqdn string = postgres.outputs.fqdn
output containerAppName string = containerApps.outputs.appName
output containerAppFqdn string = containerApps.outputs.appFqdn
output identityPrincipalId string = identity.outputs.principalId
