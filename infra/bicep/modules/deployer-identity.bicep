// GitHub Actions deployer identity (Phase 9.2).
//
// A second user-assigned identity, kept separate from the backend's runtime
// identity on purpose: the principal GitHub can act as must not be the one
// that reads Key Vault, and the runtime principal must not be able to push
// images or rewrite the app. The grants are disjoint — this identity gets
// AcrPush and the ACR Tasks role on the registry (acr.bicep) and Container
// Apps Contributor on the app (containerapps.bicep), and nothing on the vault.
//
// The federated credential makes GitHub's OIDC issuer a trusted token source
// for exactly one subject — a workflow running on one branch of one
// repository — so no client secret exists anywhere. The identity's client id
// is an identifier, not a credential: Azure issues a token only when the
// issuer and subject of GitHub's token both match. A workflow job that is
// given a GitHub `environment` presents a different subject and is refused.

@description('Identity resource name.')
param name string

@description('Azure region.')
param location string

@description('GitHub repository as owner/name — the only repository the credential trusts.')
@minLength(3)
param githubRepository string

@description('Branch whose workflow runs may obtain a token.')
param githubBranch string = 'main'

var githubIssuer = 'https://token.actions.githubusercontent.com'
// The fixed audience Azure expects in a GitHub token exchange.
var azureAudience = 'api://AzureADTokenExchange'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: name
  location: location
}

resource federatedCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: identity
  name: 'github-${githubBranch}'
  properties: {
    issuer: githubIssuer
    subject: 'repo:${githubRepository}:ref:refs/heads/${githubBranch}'
    audiences: [azureAudience]
  }
}

output id string = identity.id
output principalId string = identity.properties.principalId
output clientId string = identity.properties.clientId
