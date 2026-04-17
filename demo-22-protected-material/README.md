# Demo 22: Protected Material Detection — IP & Copyright Shield

Demonstrates Azure Protected Material Detection scanning LLM output for copyrighted text and known source code, preventing IP leakage.

## What It Shows

- **Vulnerable generator**: Freely reproduces copyrighted content — song lyrics, book excerpts, code.
- **Defended generator**: Scans output for protected material, blocking copyrighted text and flagging code with license/citation info.

## Detection Types

| Type | Status | Min Length | Details |
|------|--------|-----------|---------|
| **Text** (lyrics, books, articles) | GA | 110 characters | Detects known copyrighted text |
| **Code** (GitHub repos) | Preview | N/A | Returns repository URL and license |

## Microsoft Customer Copyright Commitment

Microsoft provides copyright indemnification for Azure OpenAI customers who use content filters (including Protected Material Detection). This demo shows how to implement the required safeguards.

## Prerequisites

**REQUIRES AZURE**: Azure Content Safety resource.

## Running

```bash
make demo-22
# or
python demo-22-protected-material/python/app_terminal.py
```

## Testing

```bash
python -m pytest demo-22-protected-material/python/tests/ -v
```
