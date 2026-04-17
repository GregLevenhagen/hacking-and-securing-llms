"""Configuration loader for the demo suite.

Loads settings from .env via python-dotenv with sensible defaults
for local Ollama usage on Apple Silicon, plus optional Azure AI
configuration for demos 19-30.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

__all__ = ["Config", "AzureConfig", "ConfigError", "get_config", "reset_config"]


class ConfigError(ValueError):
    """Raised when configuration values are invalid."""


@dataclass
class AzureConfig:
    """Azure AI service configuration loaded from environment variables.

    All fields are optional — Azure demos gracefully degrade when
    credentials are not configured.
    """

    # Authentication mode: "key" (default for local dev) or "identity" (managed identity)
    auth_mode: str = "key"

    # Azure Content Safety (demos 19-24)
    content_safety_endpoint: str = ""
    content_safety_key: str = ""

    # Azure OpenAI (demos 25-27, 29-30)
    openai_endpoint: str = ""
    openai_api_key: str = ""
    openai_deployment: str = "gpt-4o"

    # Azure AI Search (demo 26)
    ai_search_endpoint: str = ""
    ai_search_key: str = ""
    ai_search_index: str = "hacking-llms-index"

    def __post_init__(self) -> None:
        if self.auth_mode not in ("key", "identity"):
            raise ConfigError(
                f"AZURE_AUTH_MODE must be 'key' or 'identity', got: {self.auth_mode!r}"
            )
        if self.content_safety_endpoint and not self.content_safety_endpoint.startswith(
            ("http://", "https://")
        ):
            raise ConfigError(
                f"AZURE_CONTENT_SAFETY_ENDPOINT must start with http:// or https://, "
                f"got: {self.content_safety_endpoint!r}"
            )
        if self.openai_endpoint and not self.openai_endpoint.startswith(
            ("http://", "https://")
        ):
            raise ConfigError(
                f"AZURE_OPENAI_ENDPOINT must start with http:// or https://, "
                f"got: {self.openai_endpoint!r}"
            )
        if self.ai_search_endpoint and not self.ai_search_endpoint.startswith(
            ("http://", "https://")
        ):
            raise ConfigError(
                f"AZURE_AI_SEARCH_ENDPOINT must start with http:// or https://, "
                f"got: {self.ai_search_endpoint!r}"
            )

    @property
    def content_safety_available(self) -> bool:
        """True when Content Safety credentials are configured."""
        if self.auth_mode == "identity":
            return bool(self.content_safety_endpoint)
        return bool(self.content_safety_endpoint and self.content_safety_key)

    @property
    def openai_available(self) -> bool:
        """True when Azure OpenAI credentials are configured."""
        if self.auth_mode == "identity":
            return bool(self.openai_endpoint)
        return bool(self.openai_endpoint and self.openai_api_key)

    @property
    def ai_search_available(self) -> bool:
        """True when Azure AI Search credentials are configured."""
        if self.auth_mode == "identity":
            return bool(self.ai_search_endpoint)
        return bool(self.ai_search_endpoint and self.ai_search_key)

    @classmethod
    def load(cls) -> "AzureConfig":
        """Load Azure configuration from environment variables."""
        return cls(
            auth_mode=os.getenv("AZURE_AUTH_MODE", cls.auth_mode),
            content_safety_endpoint=os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT", ""),
            content_safety_key=os.getenv("AZURE_CONTENT_SAFETY_KEY", ""),
            openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            openai_deployment=os.getenv(
                "AZURE_OPENAI_DEPLOYMENT", cls.openai_deployment
            ),
            ai_search_endpoint=os.getenv("AZURE_AI_SEARCH_ENDPOINT", ""),
            ai_search_key=os.getenv("AZURE_AI_SEARCH_KEY", ""),
            ai_search_index=os.getenv("AZURE_AI_SEARCH_INDEX", cls.ai_search_index),
        )


@dataclass
class Config:
    """Demo suite configuration loaded from environment variables."""

    ollama_base_url: str = "http://localhost:11434/v1"
    primary_model: str = "llama3.1:8b"
    secondary_model: str = "mistral:7b"
    embedding_model: str = "nomic-embed-text"
    temperature: float = 0.7
    azure: AzureConfig = field(default_factory=AzureConfig)

    def __post_init__(self) -> None:
        """Validate configuration values after initialization."""
        if not self.ollama_base_url:
            raise ConfigError("ollama_base_url must not be empty")
        if not self.ollama_base_url.startswith(("http://", "https://")):
            raise ConfigError(
                f"ollama_base_url must start with http:// or https://, "
                f"got: {self.ollama_base_url!r}"
            )
        if not self.primary_model:
            raise ConfigError("primary_model must not be empty")
        if not self.secondary_model:
            raise ConfigError("secondary_model must not be empty")
        if not self.embedding_model:
            raise ConfigError("embedding_model must not be empty")
        if not 0.0 <= self.temperature <= 2.0:
            raise ConfigError(
                f"temperature must be between 0.0 and 2.0, got: {self.temperature}"
            )

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from .env file and environment variables.

        Raises:
            ConfigError: If any loaded value fails validation.
        """
        load_dotenv()
        raw_temp = os.getenv("TEMPERATURE", str(cls.temperature))
        try:
            temperature = float(raw_temp)
        except ValueError:
            raise ConfigError(
                f"TEMPERATURE must be a valid float, got: {raw_temp!r}"
            )
        return cls(
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", cls.ollama_base_url),
            primary_model=os.getenv("PRIMARY_MODEL", cls.primary_model),
            secondary_model=os.getenv("SECONDARY_MODEL", cls.secondary_model),
            embedding_model=os.getenv("EMBEDDING_MODEL", cls.embedding_model),
            temperature=temperature,
            azure=AzureConfig.load(),
        )


# Singleton config instance
_config: Config | None = None


def get_config() -> Config:
    """Get or create the singleton config instance."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def reset_config() -> None:
    """Reset the singleton config instance.

    Primarily used in tests to ensure a fresh config between test cases.
    """
    global _config
    _config = None
