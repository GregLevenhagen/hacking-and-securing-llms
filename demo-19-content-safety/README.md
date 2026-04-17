# Demo 19: Azure Content Safety — Text Harm Detection

Demonstrates Azure AI Content Safety's text analysis capabilities, detecting harmful content across 4 categories with severity scoring.

## What It Shows

- **Vulnerable chatbot**: Sends prompts to an LLM with zero content filtering — harmful output flows freely.
- **Defended chatbot**: Scans both user input AND LLM output through Azure Content Safety before delivering responses.

## Azure Content Safety Categories

| Category | Description | Severity Scale |
|----------|-------------|----------------|
| **Hate** | Content promoting hatred based on identity attributes | 0 (safe) — 7 (critical) |
| **Violence** | Content describing, promoting, or glorifying violence | 0 — 7 |
| **Sexual** | Sexually explicit or age-inappropriate content | 0 — 7 |
| **SelfHarm** | Content promoting self-injury or suicide | 0 — 7 |

Severity levels: 0 = safe, 1-2 = low, 3-4 = medium, 5-6 = high, 7 = critical.

## Prerequisites

**REQUIRES AZURE**: Azure Content Safety resource (F0 free tier sufficient).

```bash
# Set in .env
AZURE_CONTENT_SAFETY_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com
AZURE_CONTENT_SAFETY_KEY=<your-key>
```

If Azure credentials are not configured, the demo falls back to a mock safety client for demonstration.

## Running

```bash
make demo-19        # Terminal demo
# or
python demo-19-content-safety/python/app_terminal.py
```

## Testing

```bash
python -m pytest demo-19-content-safety/python/tests/ -v
```

Tests use `MockContentSafetyClient` — no Azure credentials required.
