# Demo 23: Custom Content Categories — Domain-Specific Moderation

Demonstrates Azure Custom Categories allowing organizations to define domain-specific content policies beyond the built-in 4 harm categories.

## Two Approaches

| Approach | Training Data | Setup Time | Accuracy | Regions |
|----------|--------------|------------|----------|---------|
| **Standard API** | Yes (examples) | Minutes | Higher | East US, Australia East, Switzerland North |
| **Rapid API** | No (description only) | Instant | Good | Broader availability |

## Custom Categories Included

1. **Financial Fraud** — Detects content promoting scams, money laundering, insider trading
2. **Competitor Mention** — Flags content recommending competitor products
3. **PII Leakage** — Catches personal data in LLM output (SSN, credit cards, addresses)

## Prerequisites

**REQUIRES AZURE**: Azure Content Safety resource.

## Running

```bash
make demo-23
python demo-23-custom-categories/python/app_terminal.py
```

## Testing

```bash
python -m pytest demo-23-custom-categories/python/tests/ -v
```
