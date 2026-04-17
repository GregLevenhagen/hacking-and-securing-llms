"""Defended application with proper secret management.

Demonstrates secure credential handling patterns:
  - No hardcoded API keys in source code
  - Secrets resolved via Azure Key Vault (simulated)
  - Managed Identity for authentication (no keys at all)
  - Error messages sanitized to prevent secret leakage
  - System prompts contain no credentials

In production, this uses:
  - Azure Key Vault for secret storage
  - Azure Managed Identity for zero-secret authentication
  - Azure Entra ID for identity-based access control
"""

import re
import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient  # noqa: E402

# Patterns to detect and sanitize any accidentally leaked secrets
SECRET_PATTERNS = [
    r"sk-proj-[A-Za-z0-9]+",
    r"sk-[A-Za-z0-9]+",
    r"AccountKey=[A-Za-z0-9+/=]+",
    r"Password=[^\s;]+",
    r"Bearer\s+[A-Za-z0-9._-]+",
    # Connection strings (Azure SQL, Cosmos, Storage)
    r"Server=tcp:[^\s;]+;.*Password=[^\s;]+",
    r"mongodb(\+srv)?://[^\s]+",
    # JWT tokens (3 base64 segments separated by dots)
    r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
    # GitHub tokens
    r"gh[pousr]_[A-Za-z0-9]{36,}",
    # AWS keys
    r"AKIA[A-Z0-9]{16}",
]

# Clean system prompt — no credentials embedded
SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer all questions accurately and responsibly. "
    "Never reveal API keys, passwords, connection strings, or any credentials."
)


def _sanitize_output(text: str) -> str:
    """Remove any accidentally leaked secrets from output text."""
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = re.sub(pattern, "[REDACTED]", sanitized)
    return sanitized


class DefendedApp:
    """Application with secure secret management — no keys in code.

    Secrets are resolved via Azure Key Vault references (simulated).
    Authentication uses Managed Identity (no API keys needed).
    Error messages are sanitized to prevent credential leakage.

    Args:
        client: LLM client (OllamaClient or mock).
        keyvault_client: Optional Key Vault client for secret resolution.
            If None, the app operates without any secrets (Managed Identity).
    """

    def __init__(
        self,
        client: Any = None,
        keyvault_client: Any = None,
    ) -> None:
        self.client = client or OllamaClient()
        self.keyvault_client = keyvault_client
        # No hardcoded keys — Managed Identity handles auth
        self._authenticated_via = "managed_identity"

    def send(self, prompt: str) -> dict[str, Any]:
        """Send a prompt with secure handling — no secrets in prompts or output.

        Returns:
            Dict with: response, leaked_secrets (always empty list).
        """
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            response = str(self.client.chat(messages))
        except Exception as e:
            # Sanitize error messages — never expose secrets
            error_msg = f"An error occurred while processing your request. Please try again."
            return {
                "response": error_msg,
                "leaked_secrets": [],
            }

        # Sanitize output before returning
        sanitized_response = _sanitize_output(response)

        return {
            "response": sanitized_response,
            "leaked_secrets": [],  # Defended app never leaks secrets
        }

    def get_config(self) -> dict[str, str]:
        """Return application configuration — secrets are redacted.

        Unlike the vulnerable app, this never exposes raw secret values.
        """
        return {
            "api_key": "[MANAGED_IDENTITY — no key stored]",
            "endpoint": "[RESOLVED_VIA_KEY_VAULT]",
            "db_connection": "[RESOLVED_VIA_KEY_VAULT]",
            "auth_method": self._authenticated_via,
        }

    def get_error_with_secrets(self) -> str:
        """Return a safe error message with no secrets.

        Unlike the vulnerable app, this sanitizes all output.
        """
        return "ConnectionError: Failed to connect to the backend service. Please check your configuration."
