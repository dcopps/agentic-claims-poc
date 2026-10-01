// Log Analytics workspace (Phase 9.1).
//
// A Container Apps managed environment needs a log destination; the workspace
// receives container stdout/stderr (the app's structured logs). Phase 9.2 adds
// Application Insights on top. Pay-per-GB with the free 5 GB/month allowance,
// which the prototype's log volume never approaches.

@description('Workspace resource name.')
param name string

@description('Azure region.')
param location string

// 30 days is the service minimum for PerGB2018 and plenty for demo diagnosis.
var retentionDays = 30

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: name
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionDays
  }
}

output name string = workspace.name
output id string = workspace.id
