# Hacking and Securing LLMs: Live Attacks, Broken Defenses, and Safer AI Systems

Modern LLM applications can chat, reason, retrieve data, call tools, and take autonomous action — which also means they can be manipulated, confused, and exploited in entirely new ways.

This repository contains the demos, code, and supporting materials for a conference session and workshop bundle that walks through realistic attacks against LLM systems and the defensive patterns that actually work.

## Demo Hub

The **Demo Hub** is a unified web interface that hosts all 30 demos in a single Flask application. It features sidebar navigation, a hacker/cyberpunk aesthetic with matrix rain and neon styling, and real-time SSE streaming for LLM responses.

```bash
make setup        # Create conda environments (~5 min first run)
make demo-hub     # Launch the Demo Hub on localhost:2600
```

Open [http://localhost:2600](http://localhost:2600) to browse all demos.

## Demo Index

The repo currently includes 30 demos split into four groups:

- **01–05 Attacks**: prompt injection, RAG poisoning, prompt extraction, and agent exploitation
- **06–10 Defenses**: input filtering, RAG hardening, output validation, approval gates, and secure architecture patterns
- **11–18 Advanced Attacks**: denial of service, jailbreaks, hallucination exploitation, supply-chain attacks, XSS, privilege escalation, multi-agent manipulation, and probing
- **19–30 Azure Defenses**: Azure AI Content Safety, Prompt Shields, groundedness, protected material checks, secure RAG, identity, APIM AI gateway, and Foundry-focused demos

The Demo Hub manifest in [demo-hub/blueprints/__init__.py](demo-hub/blueprints/__init__.py) is the authoritative list of routes and demo names.

## Getting Started

See [SETUP.md](SETUP.md) for full prerequisites and installation instructions. Quick start:

```bash
# 1. Install Ollama and pull required models
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull nomic-embed-text

# 2. Copy environment template
cp .env.example .env

# 3. Create local conda environments
make setup

# 4. Launch the Demo Hub
make demo-hub
```

`make setup` prepares the shared environment plus dedicated local environments for demos `01` through `18`. Demos `19` through `30` use the shared environment and optional Azure credentials from `.env`.

Individual demos can also be run standalone via `make demo-01` through `make demo-30`.

## Testing

```bash
make test          # All unit tests (no Ollama required)
make test-hub      # Demo Hub smoke tests
make test-demo-03  # Tests for a single demo
make test-e2e      # Playwright E2E tests for web UI demos
make lint          # Run mypy typecheck on shared library
make status        # Show which demos are implemented vs stubbed
```

## Project Structure

```
├── demo-hub/                   # Unified web interface for all demos
│   ├── app.py                  # Flask app factory with ChoiceLoader
│   ├── blueprints/             # One Flask Blueprint per demo (demo_01.py … demo_30.py)
│   │   └── __init__.py         # DEMO_MANIFEST — ordered list of all 30 demos
│   ├── templates/              # Per-demo templates + shared partials
│   │   ├── hub_base.html       # Hub layout with sidebar navigation
│   │   ├── hub_index.html      # Landing page with attack/defense cards
│   │   ├── _comparison.html    # Reusable side-by-side comparison (vuln vs defended)
│   │   └── demo_NN/index.html  # Individual demo UIs
│   ├── tests/                  # Hub smoke tests (pytest)
│   └── environment.yml         # Conda env for the Demo Hub
│
├── shared/                     # Shared Python libraries, templates, and test infrastructure
│   ├── python/                 # Config, Ollama client, UI helpers, web helpers, mock client
│   │   ├── config.py           # Dataclass config loaded from .env via python-dotenv
│   │   ├── ollama_client.py    # OpenAI-compatible client with retry/backoff, streaming, embeddings
│   │   ├── ui_helpers.py       # Rich terminal UI (neon green hacker theme, side-by-side panels)
│   │   ├── web_helpers.py      # Flask app factory + SSE streaming helpers
│   │   └── testing/            # Mock Ollama client, conftest, shared test utilities
│   └── templates/              # Jinja2 base templates with hacker aesthetic
│       ├── base.html           # Full-page layout: matrix rain, scanlines, Tailwind CSS, JetBrains Mono
│       ├── chat.html           # Chat interface template
│       └── styles.css          # Custom CSS (neon glow, toast notifications, scrollbar styling)
│
├── demo-01-…/                  # Each demo is self-contained
│   ├── python/                 # Source code, environment.yml
│   │   └── tests/              # pytest suite (runs without Ollama via mock client)
│   ├── attacks/                # Attack payloads (JSON)
│   └── README.md               # Demo-specific documentation
│
├── tests/e2e/                  # Playwright E2E tests for web UI demos (09, 10)
├── Makefile                    # Setup, run, test, clean, and status targets
├── SETUP.md                    # Full setup guide
└── .env.example                # Environment variable template
```

## Architecture

The demo suite uses a layered architecture:

- **Shared library** (`shared/python/`) — Configuration management, Ollama client (OpenAI-compatible with retry logic), terminal UI helpers (Rich), and Flask/SSE web helpers. All demos import from this layer.
- **Demo modules** (`demo-NN-*/python/`) — Each demo contains its own attack/defense logic, system prompts, tools, and test suite. Demos are independent and can run standalone.
- **Demo Hub** (`demo-hub/`) — A unified Flask application that registers each demo as a Blueprint. The hub provides sidebar navigation, a landing page, and consistent styling via a shared Jinja2 template hierarchy (`base.html` → `hub_base.html` → `demo_NN/index.html`).
- **Comparison engine** (`_comparison.html`) — A reusable template for defense demos (06, 07, 08, 10) that renders side-by-side vulnerable vs. defended panels with real-time SSE streaming, defense layer indicators, and result export.

## License

MIT
