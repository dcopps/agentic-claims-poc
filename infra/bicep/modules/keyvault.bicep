// Key Vault and the backend's secrets (Phase 9.1).
//
// RBAC permission model (no access policies). The Container App's identity
// gets Key Vault Secrets User; the deploying user gets Key Vault Secrets
// Officer so the bootstrap step can read DATABASE_URL — subscription Owner
// does not confer data-plane secret access under the RBAC model. Soft delete
// is mandatory and kept at the minimum; purge protection is deliberately OFF
// so a full teardown (`az group delete` + `az keyvault purge`) frees the name.
//
// The database URL is composed here from the server FQDN and the secure admin
// password, so the connection string exists only inside the vault.

@description('Vault name: 3–24 alphanumerics and hyphens, globally unique.')
@minLength(3)
@maxLength(24)
param name string

@description('Azure region.')
param location string

@description('Principal id of the Container App identity (reads secrets).')
param appPrincipalId string

@description('Object id of the deploying user (reads and writes secrets).')
param deployerPrincipalId string

@description('Postgres server FQDN.')
param postgresFqdn string

@description('Postgres database name.')
param postgresDatabaseName string

@description('Postgres administrator login.')
param postgresAdminLogin string

@secure()
param postgresAdminPassword string

@secure()
param anthropicApiKey string

@secure()
param mistralApiKey string

// Built-in roles.
var secretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
var secretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

// Service minimum for soft-delete retention.
var softDeleteRetentionDays = 7

// Flexible Server enforces TLS; `sslmode=require` makes the client refuse
// plaintext too. The admin password is generated from a hex alphabet so it
// needs no percent-encoding here.
var databaseUrl = 'postgresql://${postgresAdminLogin}:${postgresAdminPassword}@${postgresFqdn}:5432/${postgresDatabaseName}?sslmode=require'

resource vault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: name
  location: location
  properties: {
    tenantId: tenant().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: softDeleteRetentionDays
    publicNetworkAccess: 'Enabled'
  }
}

resource databaseUrlSecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: vault
  name: 'database-url'
  properties: {
    value: databaseUrl
    contentType: 'postgresql connection string'
  }
}

resource postgresPasswordSecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: vault
  name: 'postgres-admin-password'
  properties: {
    value: postgresAdminPassword
  }
}

resource anthropicSecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: vault
  name: 'anthropic-api-key'
  properties: {
    value: anthropicApiKey
  }
}

resource mistralSecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: vault
  name: 'mistral-api-key'
  properties: {
    value: mistralApiKey
  }
}

resource appSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, appPrincipalId, secretsUserRoleId)
  scope: vault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsUserRoleId)
    principalId: appPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource deployerSecretsOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, deployerPrincipalId, secretsOfficerRoleId)
  scope: vault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', secretsOfficerRoleId)
    principalId: deployerPrincipalId
    principalType: 'User'
  }
}

output name string = vault.name
output uri string = vault.properties.vaultUri
// Versionless URIs: the Container App resolves the current version at revision
// start, so a rotated secret is picked up by a restart, not a redeploy.
output databaseUrlSecretUri string = databaseUrlSecret.properties.secretUri
output anthropicApiKeySecretUri string = anthropicSecret.properties.secretUri
output mistralApiKeySecretUri string = mistralSecret.properties.secretUri
