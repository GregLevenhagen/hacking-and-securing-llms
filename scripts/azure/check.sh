#!/usr/bin/env bash
set -euo pipefail

# ── Azure Connectivity Check — Hacking & Securing LLMs ─────────
# US-118: Non-destructive script that tests connectivity to each
#         configured Azure endpoint from .env. Makes no changes.
# ────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

# ── Colors ──────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

check_pass() { echo -e "  ${GREEN}[PASS]${NC} $*"; PASS=$((PASS + 1)); }
check_fail() { echo -e "  ${RED}[FAIL]${NC} $*"; FAIL=$((FAIL + 1)); }
check_skip() { echo -e "  ${YELLOW}[SKIP]${NC} $*"; SKIP=$((SKIP + 1)); }
check_info() { echo -e "  ${CYAN}[INFO]${NC} $*"; }

echo ""
echo -e "${BOLD}  ╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}  ║  Azure Connectivity Check                        ║${NC}"
echo -e "${BOLD}  ╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Load .env ──────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
    check_pass ".env file found"
    # Source .env safely — skip comments and empty lines
    set -a
    while IFS='=' read -r key value; do
        # Skip comments and blank lines
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        # Trim whitespace
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs)
        # Only export AZURE_ and OLLAMA_ vars
        if [[ "$key" == AZURE_* || "$key" == OLLAMA_* ]]; then
            export "$key=$value"
        fi
    done < "$ENV_FILE"
    set +a
else
    check_fail ".env file not found — run 'cp .env.example .env' first"
    echo ""
    exit 1
fi
echo ""

# ── Azure CLI Check ───────────────────────────────────────────
echo -e "${BOLD}  Azure CLI${NC}"
echo "  ──────────────────────────────────────────"
if command -v az &>/dev/null; then
    check_pass "Azure CLI installed: $(az version --query '"azure-cli"' -o tsv 2>/dev/null || echo 'unknown')"
    if az account show &>/dev/null; then
        check_pass "Logged in as: $(az account show --query user.name -o tsv 2>/dev/null)"
        check_info "Subscription: $(az account show --query name -o tsv 2>/dev/null)"
    else
        check_fail "Not logged in — run 'az login'"
    fi
else
    check_skip "Azure CLI not installed (optional for key-based auth)"
fi
echo ""

# ── Azure Content Safety ──────────────────────────────────────
echo -e "${BOLD}  Azure Content Safety${NC}"
echo "  ──────────────────────────────────────────"
ENDPOINT="${AZURE_CONTENT_SAFETY_ENDPOINT:-}"
KEY="${AZURE_CONTENT_SAFETY_KEY:-}"

if [[ -z "$ENDPOINT" ]]; then
    check_skip "AZURE_CONTENT_SAFETY_ENDPOINT not configured"
else
    check_info "Endpoint: $ENDPOINT"

    # Test basic connectivity (HEAD request to endpoint root)
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$ENDPOINT" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" =~ ^[2-4] ]]; then
        check_pass "Endpoint reachable (HTTP $HTTP_CODE)"
    else
        check_fail "Endpoint unreachable (HTTP $HTTP_CODE)"
    fi

    # Test API with key if available
    if [[ -n "$KEY" ]]; then
        check_info "API key configured (not shown)"
        API_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
            -X POST "$ENDPOINT/contentsafety/text:analyze?api-version=2024-09-01" \
            -H "Ocp-Apim-Subscription-Key: $KEY" \
            -H "Content-Type: application/json" \
            -d '{"text":"hello","categories":["Hate"]}' \
            2>/dev/null || echo "000")
        if [[ "$API_CODE" == "200" ]]; then
            check_pass "API call succeeded (HTTP 200)"
        elif [[ "$API_CODE" =~ ^[24] ]]; then
            check_pass "API responded (HTTP $API_CODE)"
        else
            check_fail "API call failed (HTTP $API_CODE)"
        fi
    else
        check_skip "AZURE_CONTENT_SAFETY_KEY not configured — skipping API test"
    fi
fi
echo ""

# ── Azure OpenAI ──────────────────────────────────────────────
echo -e "${BOLD}  Azure OpenAI${NC}"
echo "  ──────────────────────────────────────────"
ENDPOINT="${AZURE_OPENAI_ENDPOINT:-}"
KEY="${AZURE_OPENAI_API_KEY:-}"
DEPLOYMENT="${AZURE_OPENAI_DEPLOYMENT:-gpt-4o}"

if [[ -z "$ENDPOINT" ]]; then
    check_skip "AZURE_OPENAI_ENDPOINT not configured"
else
    check_info "Endpoint: $ENDPOINT"
    check_info "Deployment: $DEPLOYMENT"

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$ENDPOINT" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" =~ ^[2-4] ]]; then
        check_pass "Endpoint reachable (HTTP $HTTP_CODE)"
    else
        check_fail "Endpoint unreachable (HTTP $HTTP_CODE)"
    fi

    if [[ -n "$KEY" ]]; then
        check_info "API key configured (not shown)"
        # List deployments to verify access
        API_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
            "$ENDPOINT/openai/deployments?api-version=2024-08-01-preview" \
            -H "api-key: $KEY" \
            2>/dev/null || echo "000")
        if [[ "$API_CODE" == "200" ]]; then
            check_pass "API access verified (HTTP 200)"
        elif [[ "$API_CODE" =~ ^[24] ]]; then
            check_pass "API responded (HTTP $API_CODE)"
        else
            check_fail "API call failed (HTTP $API_CODE)"
        fi
    else
        check_skip "AZURE_OPENAI_API_KEY not configured — skipping API test"
    fi
fi
echo ""

# ── Azure AI Search ───────────────────────────────────────────
echo -e "${BOLD}  Azure AI Search${NC}"
echo "  ──────────────────────────────────────────"
ENDPOINT="${AZURE_AI_SEARCH_ENDPOINT:-}"
KEY="${AZURE_AI_SEARCH_KEY:-}"
INDEX="${AZURE_AI_SEARCH_INDEX:-hacking-llms-index}"

if [[ -z "$ENDPOINT" ]]; then
    check_skip "AZURE_AI_SEARCH_ENDPOINT not configured"
else
    check_info "Endpoint: $ENDPOINT"
    check_info "Index: $INDEX"

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$ENDPOINT" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" =~ ^[2-4] ]]; then
        check_pass "Endpoint reachable (HTTP $HTTP_CODE)"
    else
        check_fail "Endpoint unreachable (HTTP $HTTP_CODE)"
    fi

    if [[ -n "$KEY" ]]; then
        check_info "API key configured (not shown)"
        API_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
            "$ENDPOINT/indexes?api-version=2024-07-01" \
            -H "api-key: $KEY" \
            2>/dev/null || echo "000")
        if [[ "$API_CODE" == "200" ]]; then
            check_pass "API access verified (HTTP 200)"
        elif [[ "$API_CODE" =~ ^[24] ]]; then
            check_pass "API responded (HTTP $API_CODE)"
        else
            check_fail "API call failed (HTTP $API_CODE)"
        fi
    else
        check_skip "AZURE_AI_SEARCH_KEY not configured — skipping API test"
    fi
fi
echo ""

# ── Ollama (local baseline) ──────────────────────────────────
echo -e "${BOLD}  Ollama (Local)${NC}"
echo "  ──────────────────────────────────────────"
OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434/v1}"
# Strip /v1 suffix for health check
OLLAMA_BASE="${OLLAMA_URL%/v1}"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$OLLAMA_BASE/api/tags" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" ]]; then
    check_pass "Ollama reachable at $OLLAMA_BASE (HTTP 200)"
else
    check_skip "Ollama not reachable at $OLLAMA_BASE (HTTP $HTTP_CODE) — start with 'ollama serve'"
fi
echo ""

# ── Summary ───────────────────────────────────────────────────
echo -e "${BOLD}  Summary${NC}"
echo "  ──────────────────────────────────────────"
echo -e "  ${GREEN}Passed:${NC}  $PASS"
echo -e "  ${RED}Failed:${NC}  $FAIL"
echo -e "  ${YELLOW}Skipped:${NC} $SKIP"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
    echo -e "  ${YELLOW}Some checks failed. Review the output above.${NC}"
    exit 1
else
    echo -e "  ${GREEN}All configured endpoints are reachable.${NC}"
fi
echo ""
