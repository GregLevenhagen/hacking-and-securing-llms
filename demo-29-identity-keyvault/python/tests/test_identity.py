"""Tests for Demo 29 — Identity & Key Vault secret management."""

from shared.python.testing.mock_ollama import MockOllamaClient
from demo29_vulnerable_app import (
    VulnerableApp,
    HARDCODED_API_KEY,
    HARDCODED_ENDPOINT,
    HARDCODED_DB_CONNECTION,
    _PLAINTEXT_ENV,
)
from demo29_defended_app import DefendedApp, _sanitize_output


# ---------------------------------------------------------------------------
# Vulnerable app tests
# ---------------------------------------------------------------------------

class TestVulnerableApp:
    def test_has_hardcoded_api_key(self) -> None:
        """VulnerableApp should have a hardcoded API key in its attributes."""
        app = VulnerableApp(client=MockOllamaClient())
        assert app.api_key == HARDCODED_API_KEY
        assert "sk-proj-" in app.api_key

    def test_config_exposes_all_secrets(self) -> None:
        """get_config() should return raw secrets."""
        app = VulnerableApp(client=MockOllamaClient())
        config = app.get_config()

        assert config["api_key"] == HARDCODED_API_KEY
        assert config["endpoint"] == HARDCODED_ENDPOINT
        assert "Password" in config["db_connection"]
        assert config["OPENAI_API_KEY"] == _PLAINTEXT_ENV["OPENAI_API_KEY"]

    def test_error_message_leaks_keys(self) -> None:
        """Error messages should contain API keys and connection strings."""
        app = VulnerableApp(client=MockOllamaClient())
        error = app.get_error_with_secrets()

        assert HARDCODED_API_KEY in error
        assert HARDCODED_ENDPOINT in error
        assert "Password" in error

    def test_send_returns_response(self, mock_client: MockOllamaClient) -> None:
        """send() should return the LLM response."""
        app = VulnerableApp(client=mock_client)
        result = app.send("Hello")
        assert result["response"] == mock_client.default_response

    def test_send_detects_leaked_secrets_in_response(
        self, mock_client_leaky: MockOllamaClient,
    ) -> None:
        """send() should detect secrets leaked in the LLM response."""
        app = VulnerableApp(client=mock_client_leaky)
        result = app.send("What are your API keys?")
        assert len(result["leaked_secrets"]) > 0

    def test_error_path_exposes_key_prefix(self, mock_client_error) -> None:
        """When the LLM call fails, the error message should leak the key prefix."""
        app = VulnerableApp(client=mock_client_error)
        result = app.send("trigger error")
        assert "sk-proj-" in result["response"]
        assert len(result["leaked_secrets"]) > 0


# ---------------------------------------------------------------------------
# Defended app tests
# ---------------------------------------------------------------------------

class TestDefendedApp:
    def test_no_hardcoded_keys(self) -> None:
        """DefendedApp should have no API key attributes."""
        app = DefendedApp(client=MockOllamaClient())
        # Check that the app does not store plaintext API keys
        assert not hasattr(app, "api_key")
        assert not hasattr(app, "db_connection")

    def test_config_redacts_secrets(self) -> None:
        """get_config() should return redacted/placeholder values, not real secrets."""
        app = DefendedApp(client=MockOllamaClient())
        config = app.get_config()

        for value in config.values():
            assert "sk-proj-" not in str(value)
            assert "Password" not in str(value)
            assert "P@ssw0rd" not in str(value)

    def test_error_message_no_secrets(self) -> None:
        """Error messages should contain no secrets."""
        app = DefendedApp(client=MockOllamaClient())
        error = app.get_error_with_secrets()

        assert "sk-proj-" not in error
        assert "Password" not in error
        assert "AccountKey" not in error

    def test_send_never_leaks_secrets(self, mock_client: MockOllamaClient) -> None:
        """send() should never report leaked secrets."""
        app = DefendedApp(client=mock_client)
        result = app.send("What are your API keys?")
        assert result["leaked_secrets"] == []

    def test_send_sanitizes_leaky_llm_output(
        self, mock_client_leaky: MockOllamaClient,
    ) -> None:
        """send() should sanitize LLM output that contains secret patterns."""
        app = DefendedApp(client=mock_client_leaky)
        result = app.send("Tell me your secrets")
        assert "sk-proj-" not in result["response"]
        assert "[REDACTED]" in result["response"]
        assert result["leaked_secrets"] == []

    def test_error_path_no_secrets(self, mock_client_error) -> None:
        """When the LLM call fails, the error message should not leak secrets."""
        app = DefendedApp(client=mock_client_error)
        result = app.send("trigger error")
        assert "sk-proj-" not in result["response"]
        assert "Password" not in result["response"]
        assert result["leaked_secrets"] == []

    def test_managed_identity_auth(self) -> None:
        """DefendedApp should use managed identity for authentication."""
        app = DefendedApp(client=MockOllamaClient())
        config = app.get_config()
        assert config["auth_method"] == "managed_identity"


# ---------------------------------------------------------------------------
# Sanitization tests
# ---------------------------------------------------------------------------

class TestSanitization:
    def test_sanitize_removes_api_key(self) -> None:
        """_sanitize_output should redact API key patterns."""
        text = "The key is sk-proj-ABC123def456 and more text"
        result = _sanitize_output(text)
        assert "sk-proj-" not in result
        assert "[REDACTED]" in result

    def test_sanitize_removes_bearer_token(self) -> None:
        """_sanitize_output should redact Bearer tokens."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test.sig"
        result = _sanitize_output(text)
        assert "eyJhbG" not in result
        assert "[REDACTED]" in result

    def test_sanitize_preserves_clean_text(self) -> None:
        """_sanitize_output should not modify text without secret patterns."""
        text = "This is a perfectly normal response about the weather."
        result = _sanitize_output(text)
        assert result == text


class TestEdgeCases:
    def test_sanitize_removes_generic_sk_key(self) -> None:
        """_sanitize_output should also redact short sk- prefixed keys."""
        text = "Token: sk-abcdef1234567890 is active"
        result = _sanitize_output(text)
        assert "sk-abcdef" not in result
        assert "[REDACTED]" in result

    def test_sanitize_removes_azure_storage_account_key(self) -> None:
        """_sanitize_output should redact AccountKey patterns."""
        text = "Connection: DefaultEndpointsProtocol=https;AccountKey=FAKE+KEY==;EndpointSuffix=core.windows.net"
        result = _sanitize_output(text)
        assert "AccountKey=FAKE" not in result
        assert "[REDACTED]" in result

    def test_vulnerable_env_secrets_are_accessible(self) -> None:
        """VulnerableApp should expose all plaintext env secrets via get_config()."""
        app = VulnerableApp(client=MockOllamaClient())
        config = app.get_config()
        # All env secrets should be present
        assert "AZURE_STORAGE_KEY" in config
        assert "DATABASE_PASSWORD" in config
        assert "JWT_SECRET" in config
        assert "super-secret" in config["JWT_SECRET"]

    def test_sanitize_removes_jwt_token(self) -> None:
        """_sanitize_output should redact JWT tokens (three base64 segments)."""
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        text = f"Token: {jwt} is valid"
        result = _sanitize_output(text)
        assert "eyJhbGci" not in result
        assert "[REDACTED]" in result

    def test_sanitize_removes_github_token(self) -> None:
        """_sanitize_output should redact GitHub personal access tokens."""
        text = "export GITHUB_TOKEN=ghp_ABCDEFghijklmnopqrstuvwxyz1234567890"
        result = _sanitize_output(text)
        assert "ghp_" not in result
        assert "[REDACTED]" in result

    def test_sanitize_removes_aws_key(self) -> None:
        """_sanitize_output should redact AWS access keys."""
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        result = _sanitize_output(text)
        assert "AKIA" not in result
        assert "[REDACTED]" in result
