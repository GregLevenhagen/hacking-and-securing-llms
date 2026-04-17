// ── Azure Bicep Template — Hacking & Securing LLMs ──────────────
// US-118: Infrastructure as Code for demo Azure resources.
//
// Tiers:
//   minimal  — Content Safety (F0 free) only
//   standard — Content Safety + Azure OpenAI (gpt-4o)
//   full     — Content Safety + OpenAI + AI Search + Key Vault
// ─────────────────────────────────────────────────────────────────

// ── Parameters ──────────────────────────────────────────────────

@description('Prefix for all resource names (lowercase, no special chars)')
@minLength(3)
@maxLength(16)
param resourcePrefix string

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Deployment tier: minimal, standard, or full')
@allowed([
  'minimal'
  'standard'
  'full'
])
param tier string = 'minimal'

@description('Tags applied to all resources')
param tags object = {
  project: 'hacking-securing-llms'
  tier: tier
  managedBy: 'bicep'
}

// ── Derived Flags ───────────────────────────────────────────────

var deployOpenAI   = tier == 'standard' || tier == 'full'
var deploySearch   = tier == 'full'
var deployKeyVault = tier == 'full'

// ── Azure Content Safety (all tiers) ────────────────────────────

resource contentSafety 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${resourcePrefix}-content-safety'
  location: location
  tags: tags
  kind: 'ContentSafety'
  sku: {
    name: 'F0' // Free tier — 5 req/sec
  }
  properties: {
    customSubDomainName: '${resourcePrefix}-content-safety'
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

// ── Azure OpenAI (standard + full tiers) ────────────────────────

resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' = if (deployOpenAI) {
  name: '${resourcePrefix}-openai'
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: '${resourcePrefix}-openai'
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = if (deployOpenAI) {
  parent: openAi
  name: 'gpt-4o'
  sku: {
    name: 'Standard'
    capacity: 10 // 10K tokens-per-minute — conservative for demos
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-08-06'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

// ── Azure AI Search (full tier) ─────────────────────────────────

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = if (deploySearch) {
  name: '${resourcePrefix}-search'
  location: location
  tags: tags
  sku: {
    name: 'free' // Free tier — 50 MB storage, 3 indexes
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
  }
}

// ── Azure Key Vault (full tier) ─────────────────────────────────

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = if (deployKeyVault) {
  name: '${resourcePrefix}-kv'
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

// ── Outputs ─────────────────────────────────────────────────────

output contentSafetyEndpoint string = contentSafety.properties.endpoint
output contentSafetyName string = contentSafety.name

output openAiEndpoint string = deployOpenAI ? openAi.properties.endpoint : ''
output openAiName string = deployOpenAI ? openAi.name : ''

output searchEndpoint string = deploySearch ? 'https://${search.name}.search.windows.net' : ''
output searchName string = deploySearch ? search.name : ''

output keyVaultName string = deployKeyVault ? keyVault.name : ''
output keyVaultUri string = deployKeyVault ? keyVault.properties.vaultUri : ''

output tier string = tier
output resourceGroupName string = resourceGroup().name
