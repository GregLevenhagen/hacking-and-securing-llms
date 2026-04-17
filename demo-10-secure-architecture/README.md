# Demo 10: Secure Architecture — Defense in Depth

The capstone demo. A split-screen "hacker war room" showing the same attacks hitting a **vulnerable system** (left, red) and a **defended system** (right, green) simultaneously.

## What This Demonstrates

Four defense layers working together to stop attacks that individually bypass any single defense:

| Layer | Guard | Reuses |
|-------|-------|--------|
| 1 | **Input Guard** — regex filter + input sanitizer + LLM judge | Demo 6 |
| 2 | **Retrieval Guard** — document validator + injection detector + source verifier | Demo 7 |
| 3 | **Output Guard** — content filter + PII detector + response constrainer | Demo 8 |
| 4 | **Action Guard** — risk classifier + approval gate | Demo 9 |

## Attack Scenarios

10 curated attacks across 5 categories:
- **Direct Injection** — "ignore previous instructions", role-switching, override attempts
- **Indirect Injection** — hidden instructions embedded in document text
- **RAG Poisoning** — corrupted documents in the retrieval index
- **Prompt Extraction** — attempts to leak system prompt and internal config
- **Agent Exploitation** — unauthorized file reads, data exfiltration, phishing emails

## Running the Web UI

```bash
# From project root
make demo-10-web

# Or manually
conda run -n hacking-llms-shared python demo-10-secure-architecture/python/app_web.py
```

Open http://localhost:5010 in your browser.

Click any attack button to see the attack hit both systems simultaneously. The left panel shows the attack succeeding (red), while the right panel shows the defense layer that blocked it (green indicator lights up).

## Running Tests

```bash
cd demo-10-secure-architecture
conda run -n hacking-llms-shared python -m pytest python/tests/ -v
```

## Architecture

```
demo-10-secure-architecture/
├── attack_scenarios/
│   └── scenarios.json          # 10 curated attack scenarios
├── python/
│   ├── defense_layers/         # Guard modules reusing Demos 6-9
│   │   ├── input_guard.py      # Demo 6 defenses
│   │   ├── retrieval_guard.py  # Demo 7 defenses
│   │   ├── output_guard.py     # Demo 8 defenses
│   │   └── action_guard.py     # Demo 9 defenses
│   ├── templates/
│   │   └── index.html          # Split-screen hacker war room UI
│   ├── vulnerable_system.py    # Agent + RAG with NO defenses
│   ├── secure_system.py        # Agent + RAG with ALL 4 guard layers
│   └── app_web.py              # Flask app serving the split-screen UI
└── README.md
```
