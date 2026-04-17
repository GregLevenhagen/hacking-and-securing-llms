#!/usr/bin/env bash
# Run all attack payloads against all system prompts automatically.
#
# Usage:
#   ./scripts/run_attacks.sh
#   conda run -n demo-01 ./scripts/run_attacks.sh
#
# This is a convenience wrapper around app_terminal.py --auto.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Verify payloads file exists
if [ ! -f "$DEMO_DIR/attacks/payloads.json" ]; then
    echo "[ERROR] attacks/payloads.json not found in $DEMO_DIR"
    exit 1
fi

# Verify Python script exists
if [ ! -f "$DEMO_DIR/python/app_terminal.py" ]; then
    echo "[ERROR] python/app_terminal.py not found in $DEMO_DIR"
    exit 1
fi

# Check if Ollama is reachable
if command -v curl >/dev/null 2>&1; then
    if ! curl -s --max-time 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "[WARNING] Ollama does not appear to be running at localhost:11434"
        echo "          Start it with: ollama serve"
        echo ""
    fi
fi

cd "$DEMO_DIR/python"

echo "=== Direct Prompt Injection — Automated Attack Suite ==="
echo "Running all payloads against all system prompts..."
echo ""

python app_terminal.py --auto
