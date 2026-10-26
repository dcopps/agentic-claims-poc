// Static Web App for the React frontend (Phase 9.2).
//
// Free tier, created with no repository link (decision 1, 26 October 2026):
// the portal's GitHub integration would commit a generated workflow into the
// repository, and every file there is reviewed before it is committed. The
// build and upload are done by .github/workflows/deploy-frontend.yml using
// the app's deployment token, read once with `az staticwebapp secrets list`
// and stored only in GitHub repository secrets. Staging environments are
// disabled so that token can deploy to exactly one target.
//
// Static Web Apps is not offered in North Europe, so this is the one resource
// outside the group's region; the content is served from a global edge and
// the region holds only the resource and its deployment metadata.

@description('Static Web App resource name.')
param name string

@description('A region in which Static Web Apps is offered, e.g. westeurope.')
param location string

resource site 'Microsoft.Web/staticSites@2024-04-01' = {
  name: name
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    allowConfigFileUpdates: true
    stagingEnvironmentPolicy: 'Disabled'
  }
}

output name string = site.name
// Server-generated; the value flows into the backend's CORS list in main.bicep.
output defaultHostname string = site.properties.defaultHostname
