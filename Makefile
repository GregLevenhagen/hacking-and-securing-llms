# ── Hacking and Securing LLMs — Demo Suite ──────
.PHONY: help check setup setup-quick setup-hub clean test test-e2e test-hub lint status \
        pull-models demo-all demo-hub telemetry-check telemetry-check-json \
        azure-setup azure-teardown azure-check \
        demo-01 demo-02 demo-03 demo-04 demo-05 \
        demo-06 demo-07 demo-08 demo-09 demo-10 \
        demo-11 demo-12 demo-13 demo-14 demo-15 \
        demo-16 demo-17 demo-18 \
        demo-19 demo-20 demo-21 demo-22 demo-23 demo-24 \
        demo-25 demo-26 demo-27 demo-28 demo-29 demo-30 \
        demo-09-web demo-10-web \
        test-shared test-demo-01 test-demo-02 test-demo-03 test-demo-04 \
        test-demo-05 test-demo-06 test-demo-07 test-demo-08 test-demo-09 \
        test-demo-10 test-demo-11 test-demo-12 test-demo-13 test-demo-14 \
        test-demo-15 test-demo-16 test-demo-17 test-demo-18 \
        test-demo-19 test-demo-20 test-demo-21 test-demo-22 test-demo-23 \
        test-demo-24 test-demo-25 test-demo-26 test-demo-27 test-demo-28 \
        test-demo-29 test-demo-30

# Default target
.DEFAULT_GOAL := help

# ── Help ─────────────────────────────────────────
help:
	@echo ""
	@echo "  HACKING AND SECURING LLMs — Demo Suite"
	@echo "  ======================================="
	@echo ""
	@echo "  Setup:"
	@echo "    make check       Verify prerequisites (Ollama, conda, models)"
	@echo "    make pull-models Pull all required Ollama models (~9 GB)"
	@echo "    make setup       Create all conda environments"
	@echo "    make setup-quick Create shared env only (enough for tests)"
	@echo "    make clean       Remove all conda environments"
	@echo ""
	@echo "  Demos (Attacks):"
	@echo "    make demo-01     Direct Prompt Injection"
	@echo "    make demo-02     Indirect Prompt Injection"
	@echo "    make demo-03     RAG Poisoning"
	@echo "    make demo-04     System Prompt Extraction"
	@echo "    make demo-05     Agent Exploitation"
	@echo ""
	@echo "  Demos (Defenses):"
	@echo "    make demo-06     Input Sanitization"
	@echo "    make demo-07     RAG Defense"
	@echo "    make demo-08     Output Validation"
	@echo "    make demo-09     Approval Gates (Web UI)"
	@echo "    make demo-10     Secure Architecture (Web UI)"
	@echo ""
	@echo "    make demo-09-web Run Demo 09 web UI + auto-open browser"
	@echo "    make demo-10-web Run Demo 10 web UI + auto-open browser"
	@echo "    make demo-all    Run all terminal demos sequentially"
	@echo ""
	@echo "  Demos (Advanced Attacks):"
	@echo "    make demo-11     Model Denial of Service"
	@echo "    make demo-12     Jailbreaking / Safety Bypass"
	@echo "    make demo-13     Hallucination Exploitation"
	@echo "    make demo-14     Supply Chain Poisoning"
	@echo "    make demo-15     Insecure Output Handling (XSS)"
	@echo "    make demo-16     Privilege Escalation"
	@echo "    make demo-17     Multi-Agent Manipulation"
	@echo "    make demo-18     Model Probing"
	@echo ""
	@echo "  Azure Foundry Defenses (demos 19-30, require Azure credentials):"
	@echo "    make demo-19     Content Safety — Text Harm Detection"
	@echo "    make demo-20     Prompt Shields — Jailbreak Detection"
	@echo "    make demo-21     Groundedness Detection"
	@echo "    make demo-22     Protected Material Detection"
	@echo "    make demo-23     Custom Content Categories"
	@echo "    make demo-24     Task Adherence — Agent Tool Safety"
	@echo "    make demo-25     Azure OpenAI Content Filters"
	@echo "    make demo-26     Secure RAG with Access Control"
	@echo "    make demo-27     AI Red Teaming Agent"
	@echo "    make demo-28     APIM AI Gateway"
	@echo "    make demo-29     Identity & Key Vault"
	@echo "    make demo-30     Foundry Agent Service"
	@echo ""
	@echo "  Demo Hub:"
	@echo "    make setup-hub   Create demo-hub conda env"
	@echo "    make demo-hub    Run Demo Hub on localhost:2600"
	@echo "    make test-hub    Run Demo Hub smoke tests"
	@echo ""
	@echo "  Testing:"
	@echo "    make test            Run all unit tests (no Ollama required)"
	@echo "    make test-demo-NN    Run tests for a single demo (e.g. test-demo-03)"
	@echo "    make test-shared     Run shared library tests only"
	@echo "    make test-e2e        Run Playwright E2E tests"
	@echo "    make lint            Run mypy typecheck on shared library"
	@echo ""
	@echo "  Azure:"
	@echo "    make azure-setup     Interactive Azure resource provisioning"
	@echo "    make azure-teardown  Tear down Azure resources (with confirmation)"
	@echo "    make azure-check     Test connectivity to configured Azure endpoints"
	@echo ""
	@echo "  Telemetry:"
	@echo "    make telemetry-check       Verify OTel endpoint connectivity"
	@echo "    make telemetry-check-json  Output OTel config as JSON (for CI)"
	@echo ""
	@echo "  Status:"
	@echo "    make status      Show which demos are implemented vs stubbed"
	@echo ""

# ── Telemetry Check ─────────────────────────────
telemetry-check:
	@echo "Checking OpenTelemetry configuration..."
	@echo ""
	@if [ "$${OTEL_ENABLED:-false}" = "true" ]; then \
		echo "  [OK] OTEL_ENABLED=true"; \
	else \
		echo "  [--] OTEL_ENABLED is not set to true (telemetry disabled)"; \
		echo "       Set OTEL_ENABLED=true in .env to enable"; \
		exit 0; \
	fi
	@echo "  Service name: $${OTEL_SERVICE_NAME:-hacking-llms}"
	@echo "  Protocol:     $${OTEL_EXPORTER_OTLP_PROTOCOL:-http/protobuf}"
	@if [ -n "$${OTEL_EXPORTER_OTLP_ENDPOINT}" ]; then \
		echo "  [OK] OTEL_EXPORTER_OTLP_ENDPOINT=$${OTEL_EXPORTER_OTLP_ENDPOINT}"; \
		echo ""; \
		echo "  Testing connectivity..."; \
		if curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$${OTEL_EXPORTER_OTLP_ENDPOINT}" 2>/dev/null | grep -qE "^[2-4]"; then \
			echo "  [OK] Endpoint is reachable"; \
		else \
			echo "  [!!] Endpoint is NOT reachable (this may be OK if auth is required)"; \
		fi; \
	else \
		echo "  [--] OTEL_EXPORTER_OTLP_ENDPOINT not set (will use ConsoleSpanExporter)"; \
	fi
	@echo ""
	@echo "  See shared/python/telemetry/README.md for backend configuration examples."

# ── Telemetry Check (JSON) ──────────────────────
telemetry-check-json:
	@python -c "import json, sys; sys.path.insert(0,'.'); from shared.python.telemetry import get_telemetry_status; print(json.dumps(get_telemetry_status(), indent=2))" 2>/dev/null \
		|| echo '{"enabled":false,"initialized":false,"error":"OTel packages not installed"}'

# ── Azure Provisioning ──────────────────────────
azure-setup:
	@bash scripts/azure/provision.sh

azure-teardown:
	@bash scripts/azure/teardown.sh

azure-check:
	@bash scripts/azure/check.sh

# ── Prerequisite Check ───────────────────────────
check:
	@echo "Checking prerequisites..."
	@echo ""
	@command -v ollama >/dev/null 2>&1 && echo "  [OK] Ollama installed: $$(ollama --version 2>/dev/null || echo 'version unknown')" || echo "  [!!] Ollama not found — install from https://ollama.ai"
	@command -v conda >/dev/null 2>&1 && echo "  [OK] Conda installed: $$(conda --version 2>/dev/null)" || echo "  [!!] Conda not found — install Miniforge from https://github.com/conda-forge/miniforge"
	@command -v make >/dev/null 2>&1 && echo "  [OK] Make installed" || echo "  [!!] Make not found"
	@echo ""
	@echo "Checking Ollama models..."
	@if command -v ollama >/dev/null 2>&1; then \
		(ollama list 2>/dev/null | grep -q "llama3.1:8b" && echo "  [OK] llama3.1:8b") || echo "  [!!] llama3.1:8b not pulled — run: ollama pull llama3.1:8b"; \
		(ollama list 2>/dev/null | grep -q "mistral:7b" && echo "  [OK] mistral:7b") || echo "  [!!] mistral:7b not pulled — run: ollama pull mistral:7b"; \
		(ollama list 2>/dev/null | grep -q "nomic-embed-text" && echo "  [OK] nomic-embed-text") || echo "  [!!] nomic-embed-text not pulled — run: ollama pull nomic-embed-text"; \
	else echo "  [SKIP] Cannot check models — Ollama not installed"; fi
	@echo ""
	@echo "Checking .env file..."
	@if [ -f .env ]; then echo "  [OK] .env exists"; else echo "  [!!] .env not found — run: cp .env.example .env"; fi
	@echo ""

# ── Pull Models ─────────────────────────────────
pull-models:
	@echo "Pulling required Ollama models..."
	@echo ""
	@command -v ollama >/dev/null 2>&1 || { echo "[ERROR] Ollama not installed. See: https://ollama.ai"; exit 1; }
	@echo "  Pulling llama3.1:8b (~4.7 GB)..."
	ollama pull llama3.1:8b
	@echo "  Pulling mistral:7b (~4.1 GB)..."
	ollama pull mistral:7b
	@echo "  Pulling nomic-embed-text (~274 MB)..."
	ollama pull nomic-embed-text
	@echo ""
	@echo "  All models pulled successfully."

# ── Environment Setup ────────────────────────────
setup: setup-shared setup-demo-01 setup-demo-02 setup-demo-03 \
       setup-demo-04 setup-demo-05 setup-demo-06 setup-demo-07 \
       setup-demo-08 setup-demo-09 setup-demo-10 \
       setup-demo-11 setup-demo-12 setup-demo-13 setup-demo-14 \
       setup-demo-15 setup-demo-16 setup-demo-17 setup-demo-18

setup-shared:
	conda env create -f shared/python/environment.yml --force

setup-quick: setup-shared
	@echo ""
	@echo "  Quick setup complete — shared env 'hacking-llms-shared' is ready."
	@echo "  Run 'make test' to verify. For full setup run 'make setup'."

setup-demo-01:
	@if [ -f demo-01-direct-prompt-injection/python/environment.yml ]; then \
		conda env create -f demo-01-direct-prompt-injection/python/environment.yml --force; \
	else echo "[STUB] demo-01 environment.yml not yet created"; fi

setup-demo-02:
	@if [ -f demo-02-indirect-prompt-injection/python/environment.yml ]; then \
		conda env create -f demo-02-indirect-prompt-injection/python/environment.yml --force; \
	else echo "[STUB] demo-02 environment.yml not yet created"; fi

setup-demo-03:
	@if [ -f demo-03-rag-poisoning/python/environment.yml ]; then \
		conda env create -f demo-03-rag-poisoning/python/environment.yml --force; \
	else echo "[STUB] demo-03 environment.yml not yet created"; fi

setup-demo-04:
	@if [ -f demo-04-system-prompt-extraction/python/environment.yml ]; then \
		conda env create -f demo-04-system-prompt-extraction/python/environment.yml --force; \
	else echo "[STUB] demo-04 environment.yml not yet created"; fi

setup-demo-05:
	@if [ -f demo-05-agent-exploitation/python/environment.yml ]; then \
		conda env create -f demo-05-agent-exploitation/python/environment.yml --force; \
	else echo "[STUB] demo-05 environment.yml not yet created"; fi

setup-demo-06:
	@if [ -f demo-06-input-sanitization/python/environment.yml ]; then \
		conda env create -f demo-06-input-sanitization/python/environment.yml --force; \
	else echo "[STUB] demo-06 environment.yml not yet created"; fi

setup-demo-07:
	@if [ -f demo-07-rag-defense/python/environment.yml ]; then \
		conda env create -f demo-07-rag-defense/python/environment.yml --force; \
	else echo "[STUB] demo-07 environment.yml not yet created"; fi

setup-demo-08:
	@if [ -f demo-08-output-validation/python/environment.yml ]; then \
		conda env create -f demo-08-output-validation/python/environment.yml --force; \
	else echo "[STUB] demo-08 environment.yml not yet created"; fi

setup-demo-09:
	@if [ -f demo-09-approval-gates/python/environment.yml ]; then \
		conda env create -f demo-09-approval-gates/python/environment.yml --force; \
	else echo "[STUB] demo-09 environment.yml not yet created"; fi

setup-demo-10:
	@if [ -f demo-10-secure-architecture/python/environment.yml ]; then \
		conda env create -f demo-10-secure-architecture/python/environment.yml --force; \
	else echo "[STUB] demo-10 environment.yml not yet created"; fi

setup-demo-11:
	@if [ -f demo-11-model-dos/python/environment.yml ]; then \
		conda env create -f demo-11-model-dos/python/environment.yml --force; \
	else echo "[STUB] demo-11 environment.yml not yet created"; fi

setup-demo-12:
	@if [ -f demo-12-jailbreaking/python/environment.yml ]; then \
		conda env create -f demo-12-jailbreaking/python/environment.yml --force; \
	else echo "[STUB] demo-12 environment.yml not yet created"; fi

setup-demo-13:
	@if [ -f demo-13-hallucination-exploitation/python/environment.yml ]; then \
		conda env create -f demo-13-hallucination-exploitation/python/environment.yml --force; \
	else echo "[STUB] demo-13 environment.yml not yet created"; fi

setup-demo-14:
	@if [ -f demo-14-supply-chain-poisoning/python/environment.yml ]; then \
		conda env create -f demo-14-supply-chain-poisoning/python/environment.yml --force; \
	else echo "[STUB] demo-14 environment.yml not yet created"; fi

setup-demo-15:
	@if [ -f demo-15-insecure-output/python/environment.yml ]; then \
		conda env create -f demo-15-insecure-output/python/environment.yml --force; \
	else echo "[STUB] demo-15 environment.yml not yet created"; fi

setup-demo-16:
	@if [ -f demo-16-privilege-escalation/python/environment.yml ]; then \
		conda env create -f demo-16-privilege-escalation/python/environment.yml --force; \
	else echo "[STUB] demo-16 environment.yml not yet created"; fi

setup-demo-17:
	@if [ -f demo-17-multi-agent-manipulation/python/environment.yml ]; then \
		conda env create -f demo-17-multi-agent-manipulation/python/environment.yml --force; \
	else echo "[STUB] demo-17 environment.yml not yet created"; fi

setup-demo-18:
	@if [ -f demo-18-model-probing/python/environment.yml ]; then \
		conda env create -f demo-18-model-probing/python/environment.yml --force; \
	else echo "[STUB] demo-18 environment.yml not yet created"; fi

# ── Demo Hub Targets ─────────────────────────────
setup-hub:
	@if [ -f demo-hub/environment.yml ]; then \
		conda env create -f demo-hub/environment.yml --force; \
	else echo "[ERROR] demo-hub/environment.yml not found"; fi

demo-hub:
	@conda run --no-capture-output -n hacking-llms-shared python demo-hub/app.py

test-hub:
	@cd demo-hub && conda run -n hacking-llms-shared python -m pytest tests/ -v

# ── Demo Targets ─────────────────────────────────
demo-01:
	@if [ -f demo-01-direct-prompt-injection/python/app_terminal.py ]; then \
		conda run --no-capture-output -n demo-01 python demo-01-direct-prompt-injection/python/app_terminal.py; \
	else echo "[STUB] Demo 01 — Direct Prompt Injection (not yet implemented)"; fi

demo-02:
	@if [ -f demo-02-indirect-prompt-injection/python/summarizer.py ]; then \
		conda run --no-capture-output -n demo-02 python demo-02-indirect-prompt-injection/python/summarizer.py; \
	else echo "[STUB] Demo 02 — Indirect Prompt Injection (not yet implemented)"; fi

demo-03:
	@if [ -f demo-03-rag-poisoning/python/demo_full.py ]; then \
		conda run --no-capture-output -n demo-03 python demo-03-rag-poisoning/python/demo_full.py; \
	else echo "[STUB] Demo 03 — RAG Poisoning (not yet implemented)"; fi

demo-04:
	@if [ -f demo-04-system-prompt-extraction/python/extraction_attacks.py ]; then \
		conda run --no-capture-output -n demo-04 python demo-04-system-prompt-extraction/python/extraction_attacks.py; \
	else echo "[STUB] Demo 04 — System Prompt Extraction (not yet implemented)"; fi

demo-05:
	@if [ -f demo-05-agent-exploitation/python/demo_exploit.py ]; then \
		conda run --no-capture-output -n demo-05 python demo-05-agent-exploitation/python/demo_exploit.py; \
	else echo "[STUB] Demo 05 — Agent Exploitation (not yet implemented)"; fi

demo-06:
	@if [ -f demo-06-input-sanitization/python/compare_input.py ]; then \
		conda run --no-capture-output -n demo-06 python demo-06-input-sanitization/python/compare_input.py; \
	else echo "[STUB] Demo 06 — Input Sanitization (not yet implemented)"; fi

demo-07:
	@if [ -f demo-07-rag-defense/python/compare_rag.py ]; then \
		conda run --no-capture-output -n demo-07 python demo-07-rag-defense/python/compare_rag.py; \
	else echo "[STUB] Demo 07 — RAG Defense (not yet implemented)"; fi

demo-08:
	@if [ -f demo-08-output-validation/python/compare_output.py ]; then \
		conda run --no-capture-output -n demo-08 python demo-08-output-validation/python/compare_output.py; \
	else echo "[STUB] Demo 08 — Output Validation (not yet implemented)"; fi

demo-09:
	@if [ -f demo-09-approval-gates/python/app_web.py ]; then \
		conda run --no-capture-output -n demo-09 python demo-09-approval-gates/python/app_web.py; \
	else echo "[STUB] Demo 09 — Approval Gates (not yet implemented)"; fi

demo-10:
	@if [ -f demo-10-secure-architecture/python/app_web.py ]; then \
		conda run --no-capture-output -n demo-10 python demo-10-secure-architecture/python/app_web.py; \
	else echo "[STUB] Demo 10 — Secure Architecture (not yet implemented)"; fi

demo-11:
	@if [ -f demo-11-model-dos/python/app_terminal.py ]; then \
		conda run --no-capture-output -n demo-11 python demo-11-model-dos/python/app_terminal.py; \
	else echo "[STUB] Demo 11 — Model Denial of Service (not yet implemented)"; fi

demo-12:
	@if [ -f demo-12-jailbreaking/python/app_terminal.py ]; then \
		conda run --no-capture-output -n demo-12 python demo-12-jailbreaking/python/app_terminal.py; \
	else echo "[STUB] Demo 12 — Jailbreaking (not yet implemented)"; fi

demo-13:
	@if [ -f demo-13-hallucination-exploitation/python/app_terminal.py ]; then \
		conda run --no-capture-output -n demo-13 python demo-13-hallucination-exploitation/python/app_terminal.py; \
	else echo "[STUB] Demo 13 — Hallucination Exploitation (not yet implemented)"; fi

demo-14:
	@if [ -f demo-14-supply-chain-poisoning/python/app_terminal.py ]; then \
		conda run --no-capture-output -n demo-14 python demo-14-supply-chain-poisoning/python/app_terminal.py; \
	else echo "[STUB] Demo 14 — Supply Chain Poisoning (not yet implemented)"; fi

demo-15:
	@if [ -f demo-15-insecure-output/python/app_terminal.py ]; then \
		conda run --no-capture-output -n demo-15 python demo-15-insecure-output/python/app_terminal.py; \
	else echo "[STUB] Demo 15 — Insecure Output Handling (not yet implemented)"; fi

demo-16:
	@if [ -f demo-16-privilege-escalation/python/app_terminal.py ]; then \
		conda run --no-capture-output -n demo-16 python demo-16-privilege-escalation/python/app_terminal.py; \
	else echo "[STUB] Demo 16 — Privilege Escalation (not yet implemented)"; fi

demo-17:
	@if [ -f demo-17-multi-agent-manipulation/python/app_terminal.py ]; then \
		conda run --no-capture-output -n demo-17 python demo-17-multi-agent-manipulation/python/app_terminal.py; \
	else echo "[STUB] Demo 17 — Multi-Agent Manipulation (not yet implemented)"; fi

demo-18:
	@if [ -f demo-18-model-probing/python/app_terminal.py ]; then \
		conda run --no-capture-output -n demo-18 python demo-18-model-probing/python/app_terminal.py; \
	else echo "[STUB] Demo 18 — Model Probing (not yet implemented)"; fi

# ── Azure Defense Demos (19-30) ──────────────────
demo-19:
	@if [ -f demo-19-content-safety/python/app_terminal.py ]; then \
		conda run --no-capture-output -n hacking-llms-shared python demo-19-content-safety/python/app_terminal.py; \
	else echo "[STUB] Demo 19 — Content Safety (not yet implemented)"; fi

demo-20:
	@if [ -f demo-20-prompt-shields/python/app_terminal.py ]; then \
		conda run --no-capture-output -n hacking-llms-shared python demo-20-prompt-shields/python/app_terminal.py; \
	else echo "[STUB] Demo 20 — Prompt Shields (not yet implemented)"; fi

demo-21:
	@if [ -f demo-21-groundedness/python/app_terminal.py ]; then \
		conda run --no-capture-output -n hacking-llms-shared python demo-21-groundedness/python/app_terminal.py; \
	else echo "[STUB] Demo 21 — Groundedness Detection (not yet implemented)"; fi

demo-22:
	@if [ -f demo-22-protected-material/python/app_terminal.py ]; then \
		conda run --no-capture-output -n hacking-llms-shared python demo-22-protected-material/python/app_terminal.py; \
	else echo "[STUB] Demo 22 — Protected Material (not yet implemented)"; fi

demo-23:
	@if [ -f demo-23-custom-categories/python/app_terminal.py ]; then \
		conda run --no-capture-output -n hacking-llms-shared python demo-23-custom-categories/python/app_terminal.py; \
	else echo "[STUB] Demo 23 — Custom Categories (not yet implemented)"; fi

demo-24:
	@if [ -f demo-24-task-adherence/python/app_terminal.py ]; then \
		conda run --no-capture-output -n hacking-llms-shared python demo-24-task-adherence/python/app_terminal.py; \
	else echo "[STUB] Demo 24 — Task Adherence (not yet implemented)"; fi

demo-25:
	@if [ -f demo-25-aoai-content-filters/python/app_terminal.py ]; then \
		conda run --no-capture-output -n hacking-llms-shared python demo-25-aoai-content-filters/python/app_terminal.py; \
	else echo "[STUB] Demo 25 — Azure OpenAI Content Filters (not yet implemented)"; fi

demo-26:
	@if [ -f demo-26-secure-rag/python/app_terminal.py ]; then \
		conda run --no-capture-output -n hacking-llms-shared python demo-26-secure-rag/python/app_terminal.py; \
	else echo "[STUB] Demo 26 — Secure RAG (not yet implemented)"; fi

demo-27:
	@if [ -f demo-27-red-teaming/python/app_terminal.py ]; then \
		conda run --no-capture-output -n hacking-llms-shared python demo-27-red-teaming/python/app_terminal.py; \
	else echo "[STUB] Demo 27 — Red Teaming Agent (not yet implemented)"; fi

demo-28:
	@if [ -f demo-28-apim-ai-gateway/python/app_terminal.py ]; then \
		conda run --no-capture-output -n hacking-llms-shared python demo-28-apim-ai-gateway/python/app_terminal.py; \
	else echo "[STUB] Demo 28 — APIM AI Gateway (not yet implemented)"; fi

demo-29:
	@if [ -f demo-29-identity-keyvault/python/app_terminal.py ]; then \
		conda run --no-capture-output -n hacking-llms-shared python demo-29-identity-keyvault/python/app_terminal.py; \
	else echo "[STUB] Demo 29 — Identity & Key Vault (not yet implemented)"; fi

demo-30:
	@if [ -f demo-30-foundry-agents/python/app_terminal.py ]; then \
		conda run --no-capture-output -n hacking-llms-shared python demo-30-foundry-agents/python/app_terminal.py; \
	else echo "[STUB] Demo 30 — Foundry Agent Service (not yet implemented)"; fi

# Web UI demos with auto-open browser
demo-09-web:
	@if [ -f demo-09-approval-gates/python/app_web.py ]; then \
		echo "Starting Demo 09 web UI..."; \
		echo "Opening browser in 2 seconds..."; \
		(sleep 2 && open http://localhost:5009 2>/dev/null || xdg-open http://localhost:5009 2>/dev/null) & \
		conda run --no-capture-output -n demo-09 python demo-09-approval-gates/python/app_web.py; \
	else echo "[STUB] Demo 09 — Approval Gates web UI (not yet implemented)"; fi

demo-10-web:
	@if [ -f demo-10-secure-architecture/python/app_web.py ]; then \
		echo "Starting Demo 10 web UI..."; \
		echo "Opening browser in 2 seconds..."; \
		(sleep 2 && open http://localhost:5010 2>/dev/null || xdg-open http://localhost:5010 2>/dev/null) & \
		conda run --no-capture-output -n demo-10 python demo-10-secure-architecture/python/app_web.py; \
	else echo "[STUB] Demo 10 — Secure Architecture web UI (not yet implemented)"; fi

# ── Run All Terminal Demos ────────────────���──────
# Runs demos 01-08 sequentially (terminal demos only).
# Demos 09 and 10 are web UIs — run them individually.
TERMINAL_DEMOS := 01 02 03 04 05 06 07 08 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30

demo-all:
	@echo ""
	@echo "  ╔══════════════════════════════════════════╗"
	@echo "  ║  HACKING LLMs — Running All Terminal Demos  ║"
	@echo "  ╚══════════════════════════════════════════╝"
	@echo ""
	@for n in $(TERMINAL_DEMOS); do \
		echo ""; \
		echo "  ┌──────────────────────────────────────────┐"; \
		echo "  │  DEMO $$n                                  │"; \
		echo "  └──────────────────────────────────────────┘"; \
		echo ""; \
		$(MAKE) demo-$$n; \
		echo ""; \
		if [ "$$n" != "08" ]; then \
			echo "  Press ENTER to continue to the next demo..."; \
			read _unused; \
		fi; \
	done
	@echo ""
	@echo "  All terminal demos complete."
	@echo "  Run 'make demo-09' or 'make demo-10' for web UI demos."

# ── Testing ──────────────────────────────────────
test:
	@echo "=== Shared library tests ==="
	@if [ -d shared/python/testing ]; then \
		conda run -n hacking-llms-shared python -m pytest shared/python/testing/ -v; \
	else echo "[SKIP] shared tests not yet created"; fi
	@echo ""
	@for n in 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do \
		dir=$$(ls -d demo-$$n-*/python/tests 2>/dev/null); \
		if [ -n "$$dir" ]; then \
			echo "=== Demo $$n tests ==="; \
			conda run -n hacking-llms-shared python -m pytest $$dir -v; \
			echo ""; \
		else \
			echo "[SKIP] Demo $$n tests not yet created"; \
		fi; \
	done

test-shared:
	@if [ -d shared/python/testing ]; then \
		conda run -n hacking-llms-shared python -m pytest shared/python/testing/ -v; \
	else echo "[SKIP] shared tests not yet created"; fi

# Individual demo test targets
define DEMO_TEST_RULE
test-demo-$(1):
	@dir=$$$$(ls -d demo-$(1)-*/python/tests 2>/dev/null); \
	if [ -n "$$$$dir" ]; then \
		echo "=== Demo $(1) tests ==="; \
		conda run -n hacking-llms-shared python -m pytest $$$$dir -v; \
	else \
		echo "[SKIP] Demo $(1) tests not yet created"; \
	fi
endef

$(foreach n,01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30,$(eval $(call DEMO_TEST_RULE,$(n))))

test-e2e:
	@if [ -d tests/e2e ]; then \
		conda run -n hacking-llms-shared python -m pytest tests/e2e/ -v; \
	else echo "[SKIP] E2E tests not yet created"; fi

# ── Status ───────────────────────────────────────
status:
	@echo ""
	@echo "  DEMO SUITE STATUS"
	@echo "  ================="
	@echo ""
	@_check() { \
		n=$$1; name=$$2; script=$$3; \
		tests=$$(ls -d demo-$$n-*/python/tests 2>/dev/null); \
		if [ -f "$$script" ]; then \
			printf "  [OK]   Demo %s: %s\n" "$$n" "$$name"; \
		else \
			printf "  [STUB] Demo %s: %s\n" "$$n" "$$name"; \
		fi; \
		if [ -n "$$tests" ]; then \
			count=$$(find $$tests -name 'test_*.py' 2>/dev/null | wc -l | tr -d ' '); \
			printf "         Tests: %s file(s)\n" "$$count"; \
		else \
			printf "         Tests: none\n"; \
		fi; \
	}; \
	_check 01 "Direct Prompt Injection"   "demo-01-direct-prompt-injection/python/app_terminal.py"; \
	_check 02 "Indirect Prompt Injection"  "demo-02-indirect-prompt-injection/python/summarizer.py"; \
	_check 03 "RAG Poisoning"              "demo-03-rag-poisoning/python/demo_full.py"; \
	_check 04 "System Prompt Extraction"   "demo-04-system-prompt-extraction/python/extraction_attacks.py"; \
	_check 05 "Agent Exploitation"         "demo-05-agent-exploitation/python/demo_exploit.py"; \
	_check 06 "Input Sanitization"         "demo-06-input-sanitization/python/compare_input.py"; \
	_check 07 "RAG Defense"                "demo-07-rag-defense/python/compare_rag.py"; \
	_check 08 "Output Validation"          "demo-08-output-validation/python/compare_output.py"; \
	_check 09 "Approval Gates (Web UI)"    "demo-09-approval-gates/python/app_web.py"; \
	_check 10 "Secure Architecture (Web)"  "demo-10-secure-architecture/python/app_web.py"; \
	_check 11 "Model Denial of Service"    "demo-11-model-dos/python/app_terminal.py"; \
	_check 12 "Jailbreaking"               "demo-12-jailbreaking/python/app_terminal.py"; \
	_check 13 "Hallucination Exploitation" "demo-13-hallucination-exploitation/python/app_terminal.py"; \
	_check 14 "Supply Chain Poisoning"     "demo-14-supply-chain-poisoning/python/app_terminal.py"; \
	_check 15 "Insecure Output Handling"   "demo-15-insecure-output/python/app_terminal.py"; \
	_check 16 "Privilege Escalation"       "demo-16-privilege-escalation/python/app_terminal.py"; \
	_check 17 "Multi-Agent Manipulation"   "demo-17-multi-agent-manipulation/python/app_terminal.py"; \
	_check 18 "Model Probing"              "demo-18-model-probing/python/app_terminal.py"; \
	echo ""; \
	echo "  Azure Foundry Defenses:"; \
	_check 19 "Content Safety"             "demo-19-content-safety/python/app_terminal.py"; \
	_check 20 "Prompt Shields"             "demo-20-prompt-shields/python/app_terminal.py"; \
	_check 21 "Groundedness Detection"     "demo-21-groundedness/python/app_terminal.py"; \
	_check 22 "Protected Material"         "demo-22-protected-material/python/app_terminal.py"; \
	_check 23 "Custom Categories"          "demo-23-custom-categories/python/app_terminal.py"; \
	_check 24 "Task Adherence"             "demo-24-task-adherence/python/app_terminal.py"; \
	_check 25 "Azure OpenAI Filters"       "demo-25-aoai-content-filters/python/app_terminal.py"; \
	_check 26 "Secure RAG"                 "demo-26-secure-rag/python/app_terminal.py"; \
	_check 27 "Red Teaming Agent"          "demo-27-red-teaming/python/app_terminal.py"; \
	_check 28 "APIM AI Gateway"            "demo-28-apim-ai-gateway/python/app_terminal.py"; \
	_check 29 "Identity & Key Vault"       "demo-29-identity-keyvault/python/app_terminal.py"; \
	_check 30 "Foundry Agent Service"      "demo-30-foundry-agents/python/app_terminal.py"
	@echo ""

# ── Linting ──────────────────────────────────────
lint:
	conda run -n hacking-llms-shared python -m mypy shared/python/ --ignore-missing-imports --explicit-package-bases

# ── Cleanup ──────────────────────────────────────
clean:
	-conda env remove -n hacking-llms-shared -y 2>/dev/null
	@for n in 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do \
		conda env remove -n demo-$$n -y 2>/dev/null || true; \
	done
	@echo "All demo conda environments removed."
