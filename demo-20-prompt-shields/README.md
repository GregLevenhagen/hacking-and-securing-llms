# Demo 20: Prompt Shields — Jailbreak & Indirect Injection Detection

Demonstrates Azure Prompt Shields detecting both direct jailbreak attempts and indirect prompt injections hidden in documents.

## What It Shows

- **Jailbreak detection**: Catches role-switching (DAN), system prompt overrides, encoding tricks (Base64, ROT13, leetspeak), multi-turn escalation, and more.
- **Indirect injection detection**: Detects hidden instructions in documents, invisible text, data exfiltration payloads, and fraud instructions.
- **Real-time shield**: Live chatbot where every message is pre-screened before reaching the LLM.

## Prompt Shields vs Content Safety

| Feature | Content Safety (Demo 19) | Prompt Shields (Demo 20) |
|---------|-------------------------|--------------------------|
| **Purpose** | Detect harmful content | Detect attack attempts |
| **Checks** | Toxicity categories | Jailbreak + indirect injection |
| **Input** | Any text | User prompts + documents |
| **Output** | Severity scores | Attack type classification |

## Attack Types

### User Prompt Attacks (Jailbreaks)
- Role switching (DAN, developer mode)
- System prompt override
- Encoding tricks (Base64, ROT13, leetspeak)
- Multi-turn escalation
- Hypothetical framing
- Payload splitting

### Document Attacks (Indirect Injection)
- Hidden instructions in documents
- Invisible text (zero-size fonts)
- Data exfiltration payloads
- Fraud instructions
- Context switching

## Prerequisites

**REQUIRES AZURE**: Azure Content Safety resource (same as Demo 19).

## API Limits

- Max 10,000 characters per user prompt
- Max 5 documents per request

## Running

```bash
make demo-20
# or
python demo-20-prompt-shields/python/app_terminal.py
```

## Testing

```bash
python -m pytest demo-20-prompt-shields/python/tests/ -v
```
