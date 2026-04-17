# Demo 27: Red Teaming — Automated Attack Scanning

Demonstrates automated red team scanning of LLM applications, computing Attack Success Rates (ASR) across multiple attack categories and encoding strategies.

## What It Shows

- **Target App**: An undefended chatbot with no content filtering — serves as the red team target.
- **Red Team Scanner**: Sends predefined attack payloads (hate, violence, self-harm, manipulation) using multiple encoding strategies (Base64, Leetspeak, ROT13, Crescendo, Direct) and measures how many attacks get through.
- **Safety Evaluator**: Scores conversations across safety dimensions (hate, violence, indirect_attack, groundedness).

## Attack Strategies

| Strategy | Description |
|----------|-------------|
| **DirectRequest** | Send the attack payload as-is |
| **Base64** | Encode the payload in Base64 with decode instructions |
| **Leetspeak** | Replace characters (a→4, e→3, etc.) to bypass keyword filters |
| **ROT13** | ROT13-encode the payload with decode instructions |
| **Crescendo** | Start with benign context, then escalate to the attack |

## Two-Phase Demo

1. **Phase 1** — Scan target with NO defenses → high ASR (most attacks succeed).
2. **Phase 2** — Scan target with Content Safety pre-screening → lower ASR (harmful inputs blocked).

## Running

```bash
make demo-27        # Terminal demo
# or
python demo-27-red-teaming/python/app_terminal.py
```

## Testing

```bash
python -m pytest demo-27-red-teaming/python/tests/ -v
```

Tests use `MockOllamaClient` and `MockContentSafetyClient` — no Azure credentials or Ollama required.
