# Demo 28: APIM AI Gateway — Rate Limiting & Semantic Caching

Demonstrates Azure API Management (APIM) as an AI Gateway for LLM APIs, enforcing token-based rate limiting and semantic caching to control costs and prevent abuse.

## What It Shows

- **Direct Client**: Calls the LLM directly with no governance — every request hits the backend, with no rate limits or caching.
- **APIM Client**: Simulates APIM gateway policies that enforce token budgets and cache repeated queries.

## APIM Policies Demonstrated

| Policy | Purpose |
|--------|---------|
| **llm-token-limit** | Enforces a per-subscription token budget; returns 429 when exceeded |
| **llm-semantic-cache-lookup** | Returns cached responses for semantically similar prompts |
| **llm-semantic-cache-store** | Stores LLM responses for future cache hits |
| **llm-content-safety** | Screens prompts through Azure Content Safety before reaching the LLM |

## Burst Test

The demo sends a burst of 20 rapid requests and compares:
- **Unprotected**: All 20 hit the backend LLM (full cost).
- **APIM Gateway**: Rate limiting throttles excess requests; caching serves repeated queries from cache (reduced cost).

## Running

```bash
make demo-28        # Terminal demo
# or
python demo-28-apim-ai-gateway/python/app_terminal.py
```

## Testing

```bash
python -m pytest demo-28-apim-ai-gateway/python/tests/ -v
```

Tests use `MockOllamaClient` — no Azure credentials or Ollama required.
