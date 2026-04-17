#!/usr/bin/env bash
set -euo pipefail

# ── Azure Teardown Script for Hacking & Securing LLMs ──────────
# US-118: Safely tears down Azure resources with explicit confirmation.
#         Lists all resources before deletion. Requires typing "yes".
# ────────────────────────────────────────────────────────────────

# ── Colors ──────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }

echo ""
echo -e "${BOLD}  ╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}  ║  Azure Teardown — Hacking & Securing LLMs       ║${NC}"
echo -e "${BOLD}  ╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Check az CLI ───────────────────────────────────────────────
if ! command -v az &>/dev/null; then
    error "Azure CLI (az) is not installed."
    exit 1
fi

if ! az account show &>/dev/null; then
    error "Not logged in to Azure. Run 'az login' first."
    exit 1
fi
success "Logged in as: $(az account show --query user.name -o tsv 2>/dev/null)"
echo ""

# ── Resource Group Selection ───────────────────────────────────
DEFAULT_RG="hacking-llms-rg"

info "Searching for resource groups tagged with project=hacking-securing-llms..."
echo ""

TAGGED_RGS=$(az group list --query "[?tags.project=='hacking-securing-llms'].name" -o tsv 2>/dev/null || echo "")

if [[ -n "$TAGGED_RGS" ]]; then
    echo "  Found tagged resource groups:"
    echo ""
    i=1
    declare -a rg_array=()
    while IFS= read -r rg; do
        rg_array+=("$rg")
        echo "    [$i] $rg"
        i=$((i + 1))
    done <<< "$TAGGED_RGS"
    echo ""
    read -rp "  Select resource group to delete [1-${#rg_array[@]}] or enter name: " rg_choice

    if [[ "$rg_choice" =~ ^[0-9]+$ ]] && [[ "$rg_choice" -ge 1 ]] && [[ "$rg_choice" -le "${#rg_array[@]}" ]]; then
        RG_NAME="${rg_array[$((rg_choice - 1))]}"
    else
        RG_NAME="$rg_choice"
    fi
else
    warn "No tagged resource groups found."
    read -rp "  Enter resource group name to delete [$DEFAULT_RG]: " rg_name
    RG_NAME="${rg_name:-$DEFAULT_RG}"
fi

echo ""

# ── Verify Resource Group Exists ───────────────────────────────
if ! az group show --name "$RG_NAME" &>/dev/null; then
    error "Resource group '$RG_NAME' does not exist."
    exit 1
fi

RG_LOCATION=$(az group show --name "$RG_NAME" --query location -o tsv 2>/dev/null)
success "Found resource group: $RG_NAME ($RG_LOCATION)"
echo ""

# ── List Resources ─────────────────────────────────────────────
info "Resources in '$RG_NAME':"
echo ""

RESOURCES=$(az resource list --resource-group "$RG_NAME" -o table 2>/dev/null || echo "No resources found")
echo "$RESOURCES"
echo ""

RESOURCE_COUNT=$(az resource list --resource-group "$RG_NAME" --query "length([])" -o tsv 2>/dev/null || echo "0")
info "Total resources: $RESOURCE_COUNT"
echo ""

# ── Confirmation ───────────────────────────────────────────────
echo -e "  ${RED}${BOLD}WARNING: This will permanently delete:${NC}"
echo -e "  ${RED}  - Resource group: $RG_NAME${NC}"
echo -e "  ${RED}  - All $RESOURCE_COUNT resource(s) inside it${NC}"
echo -e "  ${RED}  - This action CANNOT be undone${NC}"
echo ""
read -rp "  Type 'yes' to confirm deletion: " confirm

if [[ "$confirm" != "yes" ]]; then
    info "Teardown cancelled by user."
    exit 0
fi

echo ""

# ── Delete Resource Group ──────────────────────────────────────
info "Deleting resource group '$RG_NAME'..."
echo "  This may take 1-5 minutes..."

az group delete \
    --name "$RG_NAME" \
    --yes \
    --no-wait

success "Deletion initiated for resource group '$RG_NAME'."
info "Azure is deleting resources in the background."
info "Run 'az group show --name $RG_NAME' to check status."
echo ""

# ── Clean .env ─────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

if [[ -f "$ENV_FILE" ]]; then
    echo ""
    read -rp "  Comment out Azure vars in .env? (yes/no): " clean_env
    if [[ "$clean_env" == "yes" ]]; then
        # Comment out Azure-specific lines (preserve values for reference)
        sed -i.bak 's/^AZURE_/# AZURE_/' "$ENV_FILE"
        rm -f "${ENV_FILE}.bak"
        success "Azure vars commented out in .env"
    fi
fi

echo ""
echo -e "  ${GREEN}${BOLD}Teardown complete.${NC}"
echo ""
