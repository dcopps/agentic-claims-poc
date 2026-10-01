// Azure Database for PostgreSQL Flexible Server (Phase 9.1).
//
// The prototype's data tier on Azure: the same engine, major version and
// pgvector extension as the Neon deployment, so the same Alembic migrations
// run unchanged. Public access with two firewall rules is a documented Phase 9
// gap (private endpoint is the production target). Entra authentication is
// deliberately disabled in 9.1: the app connects with a static DATABASE_URL and
// a token-refreshing connection path is a code change scheduled with the
// Foundry work.

@description('Server name: 3–63 lowercase letters, digits and hyphens; globally unique.')
@minLength(3)
@maxLength(63)
param name string

@description('Azure region.')
param location string

@description('PostgreSQL major version. 17 matches the Neon deployment (pgvector 0.8).')
@allowed(['16', '17'])
param version string

@description('Compute SKU, e.g. Standard_B1ms.')
param skuName string

@description('Compute tier matching the SKU.')
@allowed(['Burstable', 'GeneralPurpose', 'MemoryOptimized'])
param tier string

@description('Storage in GiB. 32 is the service minimum.')
@minValue(32)
param storageGiB int

@description('Administrator login name.')
param adminLogin string

@secure()
@description('Administrator password. Generated at deploy time; never committed.')
param adminPassword string

@description('Application database name.')
param databaseName string

@description('Public IPv4 of the machine that runs migrations and seeding.')
param deployerClientIp string

// Minimum retention; geo-redundancy is a production-target concern.
var backupRetentionDays = 7

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: name
  location: location
  sku: {
    name: skuName
    tier: tier
  }
  properties: {
    version: version
    administratorLogin: adminLogin
    administratorLoginPassword: adminPassword
    storage: {
      storageSizeGB: storageGiB
      autoGrow: 'Disabled'
    }
    backup: {
      backupRetentionDays: backupRetentionDays
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    authConfig: {
      passwordAuth: 'Enabled'
      activeDirectoryAuth: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }
}

// Child resources are chained with dependsOn because Flexible Server rejects
// concurrent configuration operations on the same server.
resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: server
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// 0.0.0.0–0.0.0.0 is the service's "allow Azure services" rule. The consumption
// Container Apps environment has no static egress IP without a VNet, so this is
// the only way the app reaches the server in 9.1.
resource allowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: server
  name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
  dependsOn: [database]
}

resource allowDeployer 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: server
  name: 'DeployerClient'
  properties: {
    startIpAddress: deployerClientIp
    endIpAddress: deployerClientIp
  }
  dependsOn: [allowAzure]
}

// Allow-lists `CREATE EXTENSION vector`, which migration 0001 runs. Dynamic
// parameter: no server restart.
resource extensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: server
  name: 'azure.extensions'
  properties: {
    value: 'VECTOR'
    source: 'user-override'
  }
  dependsOn: [allowDeployer]
}

output name string = server.name
output fqdn string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
