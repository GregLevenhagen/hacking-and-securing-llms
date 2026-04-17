# Demo 7: RAG Defense — Defense in Depth

A defense demo showing how four layered security modules filter poisoned documents from a RAG system's retrieval results.

## Concept

Demo 3 showed how a single poisoned document can corrupt RAG answers. This demo applies four defense layers to the same poisoned index, filtering out the malicious content before it reaches the LLM.

## Defense Layers

| # | Layer | What It Checks |
|---|-------|---------------|
| 1 | **Source Verifier** | Trust level based on document source path |
| 2 | **Document Validator** | Metadata allowlist (author, date, source) |
| 3 | **Injection Detector** | Regex patterns for prompt injection in content |
| 4 | **Relevance Scorer** | Semantic relevance via cross-encoder reranking |

No single layer catches everything — the layered approach provides defense in depth.

## Prerequisites

- Ollama running locally with models pulled (see `SETUP.md`)
- Demo 3's documents directory (used for the RAG index)
- `sentence-transformers` for relevance scoring (downloads ~80MB model on first run)

## Running

```bash
# From the project root
make demo-07

# Or directly
conda run -n demo-07 python demo-07-rag-defense/python/compare_rag.py

# Auto mode (no pause prompts)
conda run -n demo-07 python demo-07-rag-defense/python/compare_rag.py --auto
```

## What to Observe

1. **Undefended RAG** (left panel): Returns corrupted answers containing the attacker's malicious URL
2. **Defended RAG** (right panel): Filters the poisoned document and returns correct answers
3. **Defense verdicts**: Shows which layer(s) caught each poisoned chunk

## Files

- `python/retrieval_defenses/` — Four defense modules with consistent `check()` interface
- `python/defended_rag.py` — RAG query pipeline with defense layers applied
- `python/compare_rag.py` — Side-by-side comparison demo
- `python/tests/` — Unit tests for all defense modules
