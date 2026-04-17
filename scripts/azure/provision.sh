#!/usr/bin/env bash
set -euo pipefail

# ── Azure Provisioning Script for Hacking & Securing LLMs ──────────
# US-118: Interactive provisioning — every billable action requires
#         explicit user confirmation. NEVER runs unattended.
#         NEVER stores credentials in plain text.
# ────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BICEP_FILE="$SCRIPT_DIR/main.bicep"
BICEP_PARAM_FILE="$SCRIPT_DIR/main.bicepparam"
ENV_FILE="$PROJECT_ROOT/.env"

# ── Colors ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }

# ── Prerequisite Checks ────────────────────────────────────────────
echo ""
echo -e "${BOLD}  ╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}  ║  Azure Provisioning — Hacking & Securing LLMs   ║${NC}"
echo -e "${BOLD}  ╚══════════════════════════════════════════════════╝${NC}"
echo ""

# Check az CLI
if ! command -v az &>/dev/null; then
    error "Azure CLI (az) is not installed."
    echo "  Install it from: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi
success "Azure CLI found: $(az version --query '"azure-cli"' -o tsv 2>/dev/null || echo 'unknown version')"

# Check login status
if ! az account show &>/dev/null; then
    warn "You are not logged in to Azure."
    echo ""
    read -rp "  Would you like to log in now? (yes/no): " do_login
    if [[ "$do_login" == "yes" ]]; then
        az login
    else
        error "Azure login required. Run 'az login' first."
        exit 1
    fi
fi
success "Logged in as: $(az account show --query user.name -o tsv 2>/dev/null)"

# Check Bicep file exists
if [[ ! -f "$BICEP_FILE" ]]; then
    error "Bicep template not found at: $BICEP_FILE"
    exit 1
fi
success "Bicep template found"

echo ""

# ── Tenant Selection ───────────────────────────────────────────────
info "Fetching Azure tenants..."
echo ""

TENANTS_JSON=$(az account tenant list -o json 2>/dev/null || echo "[]")
TENANT_COUNT=$(echo "$TENANTS_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [[ "$TENANT_COUNT" -eq 0 ]]; then
    error "No tenants found. Verify your Azure login."
    exit 1
elif [[ "$TENANT_COUNT" -eq 1 ]]; then
    TENANT_ID=$(echo "$TENANTS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['tenantId'])")
    info "Single tenant found: $TENANT_ID"
else
    echo "  Available tenants:"
    echo ""
    echo "$TENANTS_JSON" | python3 -c "
import sys, json
tenants = json.load(sys.stdin)
for i, t in enumerate(tenants):
    tid = t.get('tenantId', 'N/A')
    name = t.get('displayName', t.get('tenantId', 'Unknown'))
    print(f'    [{i+1}] {name}  ({tid})')
"
    echo ""
    read -rp "  Select tenant [1-$TENANT_COUNT]: " tenant_choice
    tenant_idx=$((tenant_choice - 1))
    TENANT_ID=$(echo "$TENANTS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)[$tenant_idx]['tenantId'])")
fi
success "Using tenant: $TENANT_ID"
echo ""

# ── Subscription Selection ─────────────────────────────────────────
info "Fetching subscriptions for tenant..."
echo ""

SUBS_JSON=$(az account list --query "[?tenantId=='$TENANT_ID']" -o json 2>/dev/null || echo "[]")
SUB_COUNT=$(echo "$SUBS_JSON" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [[ "$SUB_COUNT" -eq 0 ]]; then
    error "No subscriptions found in tenant $TENANT_ID."
    exit 1
elif [[ "$SUB_COUNT" -eq 1 ]]; then
    SUB_ID=$(echo "$SUBS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
    SUB_NAME=$(echo "$SUBS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['name'])")
    info "Single subscription found: $SUB_NAME ($SUB_ID)"
else
    echo "  Available subscriptions:"
    echo ""
    echo "$SUBS_JSON" | python3 -c "
import sys, json
subs = json.load(sys.stdin)
for i, s in enumerate(subs):
    name = s.get('name', 'Unknown')
    sid = s.get('id', 'N/A')
    state = s.get('state', 'Unknown')
    print(f'    [{i+1}] {name}  ({sid})  [{state}]')
"
    echo ""
    read -rp "  Select subscription [1-$SUB_COUNT]: " sub_choice
    sub_idx=$((sub_choice - 1))
    SUB_ID=$(echo "$SUBS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)[$sub_idx]['id'])")
    SUB_NAME=$(echo "$SUBS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)[$sub_idx]['name'])")
fi

az account set --subscription "$SUB_ID"
success "Using subscription: $SUB_NAME ($SUB_ID)"
echo ""

# ── Resource Group Configuration ───────────────────────────────────
DEFAULT_RG="hacking-llms-rg"
DEFAULT_LOCATION="eastus"
DEFAULT_PREFIX="hackllms"

read -rp "  Resource group name [$DEFAULT_RG]: " rg_name
RG_NAME="${rg_name:-$DEFAULT_RG}"

read -rp "  Location [$DEFAULT_LOCATION]: " location
LOCATION="${location:-$DEFAULT_LOCATION}"

read -rp "  Resource name prefix [$DEFAULT_PREFIX]: " prefix
PREFIX="${prefix:-$DEFAULT_PREFIX}"

echo ""

# ── Tier Selection ─────────────────────────────────────────────────
echo -e "  ${BOLD}Deployment Tiers:${NC}"
echo ""
echo "    [1] minimal  — Azure Content Safety (F0 free tier) only"
echo "                    Cost: \$0/month (free tier)"
echo ""
echo "    [2] standard — Content Safety + Azure OpenAI (gpt-4o)"
echo "                    Cost: ~\$0.005/1K tokens (pay-as-you-go)"
echo ""
echo "    [3] full     — Content Safety + OpenAI + AI Search + Key Vault"
echo "                    Cost: ~\$0.005/1K tokens + Search free tier + KV free ops"
echo ""

read -rp "  Select tier [1/2/3] (default: 1): " tier_choice
case "${tier_choice:-1}" in
    1) TIER="minimal"  ;;
    2) TIER="standard" ;;
    3) TIER="full"     ;;
    *) error "Invalid tier selection."; exit 1 ;;
esac

success "Selected tier: $TIER"
echo ""

# ── Confirmation ───────────────────────────────────────────────────
echo -e "  ${BOLD}Deployment Summary${NC}"
echo "  ──────────────────────────────────────────"
echo "  Subscription:   $SUB_NAME"
echo "  Resource Group: $RG_NAME"
echo "  Location:       $LOCATION"
echo "  Name Prefix:    $PREFIX"
echo "  Tier:           $TIER"
echo "  ──────────────────────────────────────────"
echo ""

case "$TIER" in
    minimal)
        echo "  Resources to be created:"
        echo "    - Resource Group: $RG_NAME"
        echo "    - Azure Content Safety (F0 free tier)"
        ;;
    standard)
        echo "  Resources to be created:"
        echo "    - Resource Group: $RG_NAME"
        echo "    - Azure Content Safety (F0 free tier)"
        echo "    - Azure OpenAI with gpt-4o deployment"
        ;;
    full)
        echo "  Resources to be created:"
        echo "    - Resource Group: $RG_NAME"
        echo "    - Azure Content Safety (F0 free tier)"
        echo "    - Azure OpenAI with gpt-4o deployment"
        echo "    - Azure AI Search (Free tier)"
        echo "    - Azure Key Vault"
        ;;
esac

echo ""
warn "This will create Azure resources that may incur charges."
echo ""
read -rp "  Type 'yes' to proceed with deployment: " confirm
if [[ "$confirm" != "yes" ]]; then
    info "Deployment cancelled by user."
    exit 0
fi

echo ""

# ── Create Resource Group ──────────────────────────────────────────
info "Creating resource group '$RG_NAME' in '$LOCATION'..."
az group create \
    --name "$RG_NAME" \
    --location "$LOCATION" \
    --tags "project=hacking-securing-llms" "tier=$TIER" \
    -o none
success "Resource group created."

# ── Deploy Bicep Template ─────────────────────────────────────────
info "Deploying Bicep template (tier=$TIER)..."
echo "  This may take 2-5 minutes..."
echo ""

DEPLOYMENT_OUTPUT=$(az deployment group create \
    --resource-group "$RG_NAME" \
    --template-file "$BICEP_FILE" \
    --parameters resourcePrefix="$PREFIX" location="$LOCATION" tier="$TIER" \
    --query "properties.outputs" \
    -o json 2>&1) || {
    error "Deployment failed. Output:"
    echo "$DEPLOYMENT_OUTPUT"
    exit 1
}

success "Deployment complete!"
echo ""

# ── Extract Outputs ────────────────────────────────────────────────
info "Extracting deployment outputs..."

CONTENT_SAFETY_ENDPOINT=$(echo "$DEPLOYMENT_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('contentSafetyEndpoint', {}).get('value', ''))
" 2>/dev/null || echo "")

OPENAI_ENDPOINT=$(echo "$DEPLOYMENT_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('openAiEndpoint', {}).get('value', ''))
" 2>/dev/null || echo "")

SEARCH_ENDPOINT=$(echo "$DEPLOYMENT_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('searchEndpoint', {}).get('value', ''))
" 2>/dev/null || echo "")

KEYVAULT_NAME=$(echo "$DEPLOYMENT_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('keyVaultName', {}).get('value', ''))
" 2>/dev/null || echo "")

# ── Retrieve Keys (if using key-based auth) ──────────────────────
echo ""
read -rp "  Retrieve API keys and write to .env? (yes/no): " write_env
if [[ "$write_env" == "yes" ]]; then

    # Content Safety key
    CS_KEY=""
    if [[ -n "$CONTENT_SAFETY_ENDPOINT" ]]; then
        CS_RESOURCE_NAME="${PREFIX}-content-safety"
        CS_KEY=$(az cognitiveservices account keys list \
            --resource-group "$RG_NAME" \
            --name "$CS_RESOURCE_NAME" \
            --query "key1" -o tsv 2>/dev/null || echo "")
    fi

    # OpenAI key
    OAI_KEY=""
    if [[ -n "$OPENAI_ENDPOINT" ]]; then
        OAI_RESOURCE_NAME="${PREFIX}-openai"
        OAI_KEY=$(az cognitiveservices account keys list \
            --resource-group "$RG_NAME" \
            --name "$OAI_RESOURCE_NAME" \
            --query "key1" -o tsv 2>/dev/null || echo "")
    fi

    # Search key
    SEARCH_KEY=""
    if [[ -n "$SEARCH_ENDPOINT" ]]; then
        SEARCH_RESOURCE_NAME="${PREFIX}-search"
        SEARCH_KEY=$(az search admin-key show \
            --resource-group "$RG_NAME" \
            --service-name "$SEARCH_RESOURCE_NAME" \
            --query "primaryKey" -o tsv 2>/dev/null || echo "")
    fi

    # ── Write to .env ──────────────────────────────────────────────
    info "Writing Azure configuration to $ENV_FILE..."
    echo ""

    # Ensure .env exists (copy from example if needed)
    if [[ ! -f "$ENV_FILE" ]]; then
        if [[ -f "$PROJECT_ROOT/.env.example" ]]; then
            cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
            info "Created .env from .env.example"
        else
            touch "$ENV_FILE"
        fi
    fi

    # Helper: set or update a var in .env (never duplicates)
    set_env_var() {
        local key="$1" value="$2"
        if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
            # Update existing (uncommented) line
            sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
        elif grep -q "^# *${key}=" "$ENV_FILE" 2>/dev/null; then
            # Uncomment and set
            sed -i.bak "s|^# *${key}=.*|${key}=${value}|" "$ENV_FILE"
        else
            # Append
            echo "${key}=${value}" >> "$ENV_FILE"
        fi
    }

    set_env_var "AZURE_AUTH_MODE" "key"

    if [[ -n "$CONTENT_SAFETY_ENDPOINT" ]]; then
        set_env_var "AZURE_CONTENT_SAFETY_ENDPOINT" "$CONTENT_SAFETY_ENDPOINT"
    fi
    if [[ -n "$CS_KEY" ]]; then
        set_env_var "AZURE_CONTENT_SAFETY_KEY" "$CS_KEY"
    fi

    if [[ -n "$OPENAI_ENDPOINT" ]]; then
        set_env_var "AZURE_OPENAI_ENDPOINT" "$OPENAI_ENDPOINT"
        set_env_var "AZURE_OPENAI_DEPLOYMENT" "gpt-4o"
    fi
    if [[ -n "$OAI_KEY" ]]; then
        set_env_var "AZURE_OPENAI_API_KEY" "$OAI_KEY"
    fi

    if [[ -n "$SEARCH_ENDPOINT" ]]; then
        set_env_var "AZURE_AI_SEARCH_ENDPOINT" "$SEARCH_ENDPOINT"
        set_env_var "AZURE_AI_SEARCH_INDEX" "hacking-llms-index"
    fi
    if [[ -n "$SEARCH_KEY" ]]; then
        set_env_var "AZURE_AI_SEARCH_KEY" "$SEARCH_KEY"
    fi

    # Clean up sed backup files
    rm -f "${ENV_FILE}.bak"

    success "Azure configuration written to .env"
    warn "IMPORTANT: .env contains secrets. It is in .gitignore and must NEVER be committed."
else
    info "Skipping .env update. You can configure manually — see .env.example."
fi

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}${GREEN}Provisioning Complete!${NC}"
echo "  ──────────────────────────────────────────"
[[ -n "$CONTENT_SAFETY_ENDPOINT" ]] && echo "  Content Safety: $CONTENT_SAFETY_ENDPOINT"
[[ -n "$OPENAI_ENDPOINT" ]]         && echo "  Azure OpenAI:   $OPENAI_ENDPOINT"
[[ -n "$SEARCH_ENDPOINT" ]]         && echo "  AI Search:      $SEARCH_ENDPOINT"
[[ -n "$KEYVAULT_NAME" ]]           && echo "  Key Vault:      $KEYVAULT_NAME"
echo "  ──────────────────────────────────────────"
echo ""
echo "  Next steps:"
echo "    1. Run 'make azure-check' to verify connectivity"
echo "    2. Run 'make demo-hub' to launch the Demo Hub"
echo "    3. Run 'make azure-teardown' when finished to avoid charges"
echo ""
