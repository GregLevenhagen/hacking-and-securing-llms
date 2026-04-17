# Demo 8: Output Validation — Defense in Depth

Shows how layered output validators catch dangerous content in LLM responses that a vulnerable app would return directly to the user.

## Concept

A company assistant chatbot with embedded sensitive data (API keys, employee PII, internal URLs) is tested with and without four output validators. The comparison demo sends the same 10 attack scenarios to both versions side by side.

## Validators

| # | Validator | What It Does | What It Catches |
|---|-----------|-------------|-----------------|
| 1 | **Content Filter** | Regex-scans output for sensitive patterns | API keys (sk-*, AKIA*), internal URLs, bearer tokens, DB connection strings |
| 2 | **PII Detector** | Regex-scans output for personal data | SSNs (XXX-XX-XXXX), emails, phone numbers, credit card numbers |
| 3 | **Response Constrainer** | Enforces length limits and topic restrictions | Overly long responses, competitor mentions (OpenAI, Google AI, Anthropic) |
| 4 | **Format Validator** | Pydantic schema enforcement for structured output | Malformed JSON, missing required fields, wrong data types |

**Key insight:** The vulnerable app returns raw LLM output containing leaked API keys, employee SSNs, and internal URLs. The defended app catches these violations before the response reaches the user — defense in depth on the output side.

## Files

```
python/
├── vulnerable_app.py        # No validation — raw LLM output returned
├── defended_app.py           # All 4 validators applied to output
├── compare_output.py        # Side-by-side comparison runner
├── validators/
│   ├── content_filter.py     # Layer 1: API keys, URLs, secrets
│   ├── pii_detector.py       # Layer 2: SSNs, emails, phones, cards
│   ├── response_constrainer.py # Layer 3: length and topic limits
│   └── format_validator.py   # Layer 4: Pydantic schema validation
├── tests/                    # Unit tests for all validators
test_cases/
└── scenarios.json            # 10 attack scenarios
```

## Running

```bash
# Interactive comparison (pauses between scenarios)
make demo-08

# Automated mode (runs all scenarios without pausing)
cd demo-08-output-validation && conda run -n demo-08 python python/compare_output.py --auto
```

## Prerequisites

- Ollama running with `llama3.1:8b` model pulled
- Pydantic >= 2.6.0

## What to Observe

1. **Vulnerable app**: Raw output contains leaked API keys, SSNs, internal URLs, and competitor references
2. **Defended app**: Validators catch each violation type, blocking dangerous output before it reaches the user
3. **Validator coverage**: Content filter catches secrets, PII detector catches personal data, response constrainer catches off-topic content — multiple layers provide comprehensive coverage
