// Container Apps environment and the backend Container App (Phase 9.1).
//
// Consumption-only environment logging to Log Analytics. The app runs the
// image built by `az acr build`, pulls it with the user-assigned identity,
// resolves its three secrets from Key Vault with the same identity, and
// exposes /health as the startup, readiness and liveness probe. Single
// revision mode: the demo has one live version at a time.
//
// The app is conditional on `containerImage`: pass 1 of the deploy creates
// the environment with no app (the registry must exist before an image can
// be built); pass 2 supplies the image and creates the app. No placeholder
// image is ever deployed.

@description('Managed environment name.')
param environmentName string

@description('Container App name.')
param appName string

@description('Azure region.')
param location string

@description('Log Analytics workspace name (same resource group).')
param logAnalyticsName string

@description('Resource id of the user-assigned identity.')
param identityId string

@description('Registry login server, e.g. acrx.azurecr.io.')
param acrLoginServer string

@description('Full image reference. Empty string skips the Container App.')
param containerImage string

@description('Versionless Key Vault secret URIs.')
param databaseUrlSecretUri string
param anthropicApiKeySecretUri string
param mistralApiKeySecretUri string

@description('JSON list of allowed CORS origins, as pydantic-settings parses it.')
param corsAllowedOrigins string

@description('vCPU as a decimal string, e.g. 1.0.')
param cpu string

@description('Memory, e.g. 2Gi.')
param memory string

@minValue(0)
param minReplicas int

@minValue(1)
param maxReplicas int

// Fixed in the Dockerfile (Settings.api_port default). Container Apps does not
// inject $PORT.
var targetPort = 8000

// Startup: 5 s × 24 = two minutes for image pull plus Python import. /health
// touches neither the database nor the model, so it measures process liveness.
var probes = [
  {
    type: 'Startup'
    httpGet: { path: '/health', port: targetPort }
    periodSeconds: 5
    failureThreshold: 24
  }
  {
    type: 'Readiness'
    httpGet: { path: '/health', port: targetPort }
    periodSeconds: 10
  }
  {
    type: 'Liveness'
    httpGet: { path: '/health', port: targetPort }
    periodSeconds: 30
  }
]

var deployApp = !empty(containerImage)

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsName
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = if (deployApp) {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acrLoginServer
          identity: identityId
        }
      ]
      secrets: [
        { name: 'database-url', keyVaultUrl: databaseUrlSecretUri, identity: identityId }
        { name: 'anthropic-api-key', keyVaultUrl: anthropicApiKeySecretUri, identity: identityId }
        { name: 'mistral-api-key', keyVaultUrl: mistralApiKeySecretUri, identity: identityId }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: containerImage
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'ANTHROPIC_API_KEY', secretRef: 'anthropic-api-key' }
            { name: 'MISTRAL_API_KEY', secretRef: 'mistral-api-key' }
            { name: 'CORS_ALLOWED_ORIGINS', value: corsAllowedOrigins }
          ]
          probes: probes
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output environmentName string = managedEnvironment.name
// `!` asserts non-null: the ternary already guards the conditional resource.
output appName string = deployApp ? app!.name : ''
output appFqdn string = deployApp ? app!.properties.configuration.ingress.fqdn : ''
