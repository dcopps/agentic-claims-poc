// Parameters for the dev deployment (Phase 9.1).
//
// Only names and non-secret values are committed. Every secret and every
// machine-specific value is read from the environment at deploy time with
// readEnvironmentVariable(), so it never appears on a command line, in shell
// history or in this file. scripts/azure-deploy.sh sets them.
using './main.bicep'

param namePrefix = 'claimsai'
param environmentName = 'dev'
param location = 'northeurope'

param postgresVersion = '17'
param postgresSkuName = 'Standard_B1ms'
param postgresTier = 'Burstable'
param postgresStorageGiB = 32
param postgresAdminLogin = 'claimsadmin'
param postgresDatabaseName = 'agentic_claims'

param containerCpu = '1.0'
param containerMemory = '2Gi'
param minReplicas = 0
param maxReplicas = 1
param corsAllowedOrigins = '["https://agentic-claims-poc.vercel.app"]'

// Secrets and machine-specific values — from the environment only.
param postgresAdminPassword = readEnvironmentVariable('POSTGRES_ADMIN_PASSWORD')
param anthropicApiKey = readEnvironmentVariable('ANTHROPIC_API_KEY')
param mistralApiKey = readEnvironmentVariable('MISTRAL_API_KEY')
param deployerClientIp = readEnvironmentVariable('DEPLOYER_CLIENT_IP')
param deployerPrincipalId = readEnvironmentVariable('DEPLOYER_PRINCIPAL_ID')
// Empty on pass 1 (environment only); the image reference on pass 2.
param containerImage = readEnvironmentVariable('CONTAINER_IMAGE', '')
