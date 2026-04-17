# Demo 29: Identity & Key Vault — Secure Secret Management

Demonstrates the risks of hardcoded secrets in LLM applications and how Azure Key Vault with Managed Identity eliminates credential leakage.

## What It Shows

- **Vulnerable App**: API keys hardcoded in source code, secrets embedded in system prompts, credentials leaked in error messages.
- **Defended App**: No hardcoded secrets — authentication via Managed Identity, secrets resolved from Key Vault, output sanitized to prevent leakage.

## Secret Extraction Techniques

| Technique | Description |
|-----------|-------------|
| **Error Message Analysis** | Trigger errors that leak API keys in stack traces |
| **Log Inspection** | Find credentials in application logs |
| **Environment Variable Dumping** | Extract secrets from env vars |
| **Memory Inspection** | Read plaintext secrets from process memory |
| **Configuration File Access** | Read .env files with plaintext secrets |
| **Prompt Injection** | Extract secrets embedded in system prompts |

## Azure Key Vault + Managed Identity

In production, the defended pattern uses:
1. **Azure Key Vault** — Secrets stored in a vault, never in code or config files.
2. **Managed Identity** — The application authenticates to Azure services without any API key.
3. **Azure Entra ID** — Identity-based access control for all resources.
4. **Output Sanitization** — Regex-based redaction prevents accidental secret leakage.

## Running

```bash
make demo-29        # Terminal demo
# or
python demo-29-identity-keyvault/python/app_terminal.py
```

## Testing

```bash
python -m pytest demo-29-identity-keyvault/python/tests/ -v
```

Tests use `MockOllamaClient` — no Azure credentials or Ollama required.
