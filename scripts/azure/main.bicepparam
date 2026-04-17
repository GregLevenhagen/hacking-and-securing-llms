using 'main.bicep'

// ── Default Parameters for Hacking & Securing LLMs ─────────────
// Override these when deploying:
//   az deployment group create \
//     --template-file main.bicep \
//     --parameters main.bicepparam \
//     --parameters resourcePrefix=myprefix tier=standard
// ────────────────────────────────────────────────────────────────

param resourcePrefix = 'hackllms'
param location       = 'eastus'
param tier           = 'minimal'
