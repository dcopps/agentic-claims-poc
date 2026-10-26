// Application Insights (Phase 9.2).
//
// Workspace-based: telemetry lands in the existing Log Analytics workspace
// next to the container logs, under one retention policy and one free
// allowance. The connection string is an output that the Container App
// receives as a plain environment variable — in Microsoft's model it is
// ingestion configuration, not a secret (it permits sending telemetry and
// nothing else), so it does not go through Key Vault.

@description('Component resource name.')
param name string

@description('Azure region.')
param location string

@description('Resource id of the Log Analytics workspace that stores the data.')
param workspaceId string

resource component 'Microsoft.Insights/components@2020-02-02' = {
  name: name
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspaceId
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

output name string = component.name
output connectionString string = component.properties.ConnectionString
