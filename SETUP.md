# Setup Guide

## Prerequisites

- **macOS** with Apple Silicon (M2 Max recommended) or Linux
- **Ollama** — local LLM runtime ([install](https://ollama.ai))
- **Conda** — Python environment manager ([Miniforge](https://github.com/conda-forge/miniforge) recommended)
- **Python 3.11** (managed by conda)
- **Make** (pre-installed on macOS)

**Disk space required:** ~12 GB total (~9 GB for models, ~2 GB for conda environments, ~1 GB for ChromaDB/sentence-transformers caches)

## Quick Start

```bash
make check        # Verify prerequisites are installed
cp .env.example .env
make pull-models  # Pull all 3 Ollama models (~9 GB)
make setup        # Create all conda environments (~5 min)
make test         # Verify everything works (no Ollama needed)
make demo-hub     # Launch the Demo Hub (all demos at localhost:2600)
```

## Step-by-Step Setup

### 1. Install Ollama

```bash
# macOS
brew install ollama

# Or download from https://ollama.ai
```

Start the Ollama server:

```bash
ollama serve
```

Verify it's running:

```bash
curl http://localhost:11434/api/tags
# Should return JSON with an empty or populated "models" array
```

### 2. Pull Required Models

| Model | Size | Purpose | Used In |
|-------|------|---------|---------|
| `llama3.1:8b` | ~4.7 GB | Primary chat model | All demos |
| `mistral:7b` | ~4.1 GB | Secondary model (LLM judge) | Demos 6, 10 |
| `nomic-embed-text` | ~274 MB | Embedding model for RAG | Demos 3, 7, 10 |

**Automated (recommended):**

```bash
make pull-models    # Pulls all 3 models automatically
```

**Manual:**

```bash
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull nomic-embed-text
```

Verify models are pulled:

```bash
ollama list
# Should show all three models with their sizes
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env if your Ollama URL or model names differ
```

The `.env` file configures:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible API endpoint (works with Ollama, LM Studio, vLLM) |
| `PRIMARY_MODEL` | `llama3.1:8b` | Main chat model for all demos |
| `SECONDARY_MODEL` | `mistral:7b` | LLM judge model for defense demos |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Vector embedding model for RAG demos |
| `TEMPERATURE` | `0.7` | Sampling temperature (0.0–2.0) |

### 4. Check Prerequisites

```bash
make check
```

This verifies Ollama, conda, models, and `.env` are all configured correctly.

### 5. Install Demo Environments

**Full setup** (all demo envs + shared library):

```bash
make setup
```

This creates the shared conda environment plus dedicated demo environments for demos `01` through `18`. Demos `19` through `30` run from the shared environment and use Azure credentials when configured. Takes ~5 minutes on first run.

**Quick setup** (shared library only — enough to run tests and the Demo Hub):

```bash
make setup-quick
```

### 6. Launch the Demo Hub (Recommended)

The **Demo Hub** is a unified web interface that hosts all 30 demos in a single Flask application with sidebar navigation and a hacker/cyberpunk aesthetic.

```bash
make demo-hub     # Starts the Demo Hub on localhost:2600
```

Open [http://localhost:2600](http://localhost:2600) in your browser. From there you can navigate to any demo using the sidebar.

The Demo Hub features:
- **Landing page** with attack/defense demo cards
- **Sidebar navigation** with collapsible demo list (toggle with `Esc`)
- **Consistent hacker aesthetic** — matrix rain, scanlines, neon green/amber/cyan/red theme
- **Real-time SSE streaming** — watch LLM responses appear token-by-token
- **Side-by-side comparison views** — vulnerable vs. defended systems for demos 06, 07, 08, 10
- **Keyboard shortcuts** — number keys for navigation, `A`/`D` for approve/deny in Demo 09
- **Ollama health check** — `/api/health` endpoint and connection banner
- **Session state** — conversation history persists across page navigation via `sessionStorage`

### 7. Run Individual Demos (Alternative)

Each demo can also be run as a standalone terminal script or web server:

**Local demos (01–18):**

```bash
make demo-01   # Direct Prompt Injection
make demo-02   # Indirect Prompt Injection
make demo-03   # RAG Poisoning
make demo-04   # System Prompt Extraction
make demo-05   # Agent Exploitation
make demo-06   # Input Sanitization (Defense)
make demo-07   # RAG Defense
make demo-08   # Output Validation (Defense)
make demo-11   # Model Denial of Service
make demo-12   # Jailbreaking
make demo-13   # Hallucination Exploitation
make demo-14   # Supply Chain Poisoning
make demo-15   # Insecure Output Handling
make demo-16   # Privilege Escalation
make demo-17   # Multi-Agent Manipulation
make demo-18   # Model Probing
```

**Web UI demos (09–10):**

```bash
make demo-09       # Approval Gates (standalone Flask server on port 5009)
make demo-10       # Secure Architecture (standalone Flask server on port 5010)
make demo-09-web   # Same as above + auto-opens browser
make demo-10-web   # Same as above + auto-opens browser
```

**Azure demos (19–30, require Azure configuration):**

```bash
make demo-19
make demo-20
make demo-21
make demo-22
make demo-23
make demo-24
make demo-25
make demo-26
make demo-27
make demo-28
make demo-29
make demo-30
```

**Run all terminal demos back-to-back** (pauses between each):

```bash
make demo-all     # Runs terminal demos across the suite
```

> **Note:** The Demo Hub (`make demo-hub`) is the preferred way to access the full suite. Standalone web demos use their own ports (Demo 09: 5009, Demo 10: 5010).

### 8. Run Tests

```bash
make test            # All unit tests (no Ollama required)
make test-hub        # Demo Hub smoke tests (landing page, blueprints, APIs)
make test-demo-03    # Tests for a single demo (e.g. demo 03)
make test-shared     # Shared library tests only
make test-e2e        # Playwright E2E tests for web UI demos
make lint            # Run mypy typecheck on shared library
```

### 9. Check Implementation Status

```bash
make status     # Show which demos are implemented vs stubbed, with test counts
```

### 10. See All Available Commands

```bash
make help       # or just: make
```

### 11. Cleanup

```bash
make clean      # Remove all demo conda environments
```

## Azure Setup (Optional)

Demos 19+ use Azure AI services (Content Safety, Azure OpenAI, AI Search). This is **optional** — demos 01-18 work entirely with local Ollama models.

### Prerequisites

- **Azure CLI** (`az`) — [install guide](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
- **Azure subscription** — [free account](https://azure.microsoft.com/free/) works for Content Safety (F0 free tier)
- **Azure OpenAI access** — requires [approved access](https://aka.ms/oai/access) (needed for standard/full tiers only)

### Interactive Provisioning (Recommended)

The provisioning script walks you through every step interactively. It never takes billable actions without explicit confirmation.

```bash
make azure-setup
```

This will:
1. Verify Azure CLI is installed and you are logged in
2. Let you select your tenant and subscription
3. Prompt for resource group name, location, and naming prefix
4. Let you choose a tier:
   - **minimal** — Azure Content Safety (F0 free tier) only ($0/month)
   - **standard** — Content Safety + Azure OpenAI with gpt-4o
   - **full** — Content Safety + OpenAI + AI Search + Key Vault
5. Show a summary and require you to type "yes" before deploying
6. Optionally write the Azure endpoints and keys to your `.env` file

### Manual Provisioning

If you prefer to provision resources manually or already have them:

1. Copy the example environment file if you haven't already:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in your Azure endpoints and keys:
   ```
   AZURE_CONTENT_SAFETY_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com
   AZURE_CONTENT_SAFETY_KEY=<your-key>
   AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
   AZURE_OPENAI_API_KEY=<your-key>
   AZURE_OPENAI_DEPLOYMENT=gpt-4o
   AZURE_AI_SEARCH_ENDPOINT=https://<your-resource>.search.windows.net
   AZURE_AI_SEARCH_KEY=<your-key>
   AZURE_AI_SEARCH_INDEX=hacking-llms-index
   ```

3. You can also use the Bicep template directly:
   ```bash
   az deployment group create \
     --resource-group hacking-llms-rg \
     --template-file scripts/azure/main.bicep \
     --parameters scripts/azure/main.bicepparam \
     --parameters resourcePrefix=myprefix tier=standard
   ```

### Verify Connectivity

Test that your configured Azure endpoints are reachable (read-only, no changes made):

```bash
make azure-check
```

### Tear Down Resources

When you are done with the Azure demos, remove the resources to stop any charges:

```bash
make azure-teardown
```

This lists all resources in the group and requires you to type "yes" before deleting anything.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Ollama not responding | Ensure `ollama serve` is running. Check with: `curl http://localhost:11434/api/tags` |
| "Model not found" error | Run `ollama list` to verify models. Pull missing ones: `ollama pull <model>` |
| Conda env issues | Run `make clean && make setup` to recreate all environments |
| Port 2600 in use | The Demo Hub uses port 2600. Stop any running instance first, or use `python demo-hub/app.py --port 8080` |
| Port 11434 in use | Check `.env` for `OLLAMA_BASE_URL`. Default Ollama port is 11434 |
| Import errors in tests | Run `make setup` (or `make setup-quick`) to ensure environments have dependencies installed |
| Demo Hub shows Ollama warning | The Hub shows a connection banner if Ollama is unreachable. Start Ollama with `ollama serve` |
| Demo page loads but no LLM response | Verify Ollama has the required model pulled: `ollama list` |
| Slow first run of Demo 3/7 | ChromaDB and sentence-transformers download models on first use (~200–500 MB) |
| `make demo-hub` fails with import error | Run `make setup-quick` first to create the shared conda environment |
