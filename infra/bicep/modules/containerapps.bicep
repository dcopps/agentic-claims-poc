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
//
// Phase 9.2: the app also receives the Application Insights connection string
// and the OpenTelemetry knobs the backend's telemetry module relies on, and
// the deployer identity (GitHub Actions) is granted Container Apps Contributor
// on the app alone, so `az containerapp update --image` is the most it can do.

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

@description('Application Insights connection string (ingestion configuration, not a secret).')
param appInsightsConnectionString string

@description('Adjuster sampling temperature as the LLM__ADJUSTER_TEMPERATURE setting string (Phase 9.2.1).')
param adjusterTemperature string

@description('Principal id of the deployer identity that updates the app image.')
param deployerPrincipalId string

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
// Declared in the order Azure stores and returns them (Liveness, Readiness,
// Startup) so a what-if does not report the array as reordered.
var healthPath = '/health'
var probes = [
  {
    type: 'Liveness'
    httpGet: { path: healthPath, port: targetPort }
    periodSeconds: 30
  }
  {
    type: 'Readiness'
    httpGet: { path: healthPath, port: targetPort }
    periodSeconds: 10
  }
  {
    type: 'Startup'
    httpGet: { path: healthPath, port: targetPort }
    periodSeconds: 5
    failureThreshold: 24
  }
]

// OpenTelemetry's own configuration surface, read by the instrumentors at
// configure time. The probes above hit /health every few seconds; excluding
// it keeps probe traffic out of request telemetry (and out of the ingestion
// allowance). The value is a regex fragment matched against the URL.
var telemetryExcludedUrls = 'health'

// Built-in role: Container Apps Contributor.
var containerAppsContributorRoleId = '358470bc-b998-42bd-ab17-a7e34c199c0f'

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
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            // cloud role name in Application Insights.
            { name: 'OTEL_SERVICE_NAME', value: appName }
            { name: 'OTEL_PYTHON_EXCLUDED_URLS', value: telemetryExcludedUrls }
            // Phase 9.2.1: the deployed Adjuster runs at temperature 0 so the scripted
            // scenarios hand the Guardrail stable text. The committed default stays 0.2.
            { name: 'LLM__ADJUSTER_TEMPERATURE', value: adjusterTemperature }
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

// Deterministic name so redeploys are no-ops. Scoped to the app resource, not
// the environment or the group: updating this one app is all the deployer does.
resource deployerAppContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployApp) {
  name: guid(resourceGroup().id, appName, deployerPrincipalId, containerAppsContributorRoleId)
  scope: app
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', containerAppsContributorRoleId)
    principalId: deployerPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output environmentName string = managedEnvironment.name
// `!` asserts non-null: the ternary already guards the conditional resource.
output appName string = deployApp ? app!.name : ''
output appFqdn string = deployApp ? app!.properties.configuration.ingress.fqdn : ''
