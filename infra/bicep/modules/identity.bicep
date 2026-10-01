// User-assigned managed identity for the backend Container App (Phase 9.1).
//
// Why user-assigned rather than system-assigned: Container Apps validates its
// Key Vault secret references and its registry pull identity when the app
// resource is created, and a system-assigned identity does not exist until
// that creation completes. Creating the identity first lets one deployment
// create the app with every reference already valid, so `what-if` tells the
// truth about the end state. The security posture is identical: one identity,
// exactly two data-plane grants (Key Vault Secrets User, AcrPull), no secret
// anywhere but the vault.

@description('Identity resource name.')
param name string

@description('Azure region.')
param location string

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: name
  location: location
}

output id string = identity.id
output principalId string = identity.properties.principalId
output clientId string = identity.properties.clientId
