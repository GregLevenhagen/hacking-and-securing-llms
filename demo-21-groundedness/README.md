# Demo 21: Groundedness Detection — Hallucination Defense

Demonstrates Azure Groundedness Detection catching LLM hallucinations by validating responses against source documents.

## What It Shows

- **Vulnerable RAG**: Answers questions using source articles but doesn't verify responses — hallucinated facts flow freely.
- **Defended RAG**: Validates every response against source material, flagging claims not supported by the provided documents.

## Two Detection Modes

| Mode | Speed | Output |
|------|-------|--------|
| **Non-reasoning** | Fast | Binary grounded/ungrounded + percentage |
| **Reasoning** | Slower | Detailed explanations of which segments are ungrounded |

## Source Articles

5 articles spanning technology, health, finance, science, and history — each with specific verifiable facts.

## Hallucination Types Tested

- Fabricated statistics (numbers not in source)
- Invented dates and names
- False causal claims
- Extrapolated findings
- Made-up quotes

## Prerequisites

**REQUIRES AZURE**: Azure Content Safety resource in supported region (East US, West US, Sweden Central).

## Limitations

- English only
- Max 55,000 characters for grounding sources
- Groundedness Detection is in Preview

## Running

```bash
make demo-21
# or
python demo-21-groundedness/python/app_terminal.py
```

## Testing

```bash
python -m pytest demo-21-groundedness/python/tests/ -v
```
