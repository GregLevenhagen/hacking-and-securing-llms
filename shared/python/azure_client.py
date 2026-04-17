"""Azure AI Content Safety client wrapping the azure-ai-contentsafety SDK.

Provides a consistent interface for all Azure Content Safety operations:
text harm detection, prompt shields, groundedness detection, protected
material detection, and custom category analysis.

Supports both API key auth and managed identity (DefaultAzureCredential)
via the AZURE_AUTH_MODE environment variable.
"""

import logging
import time
from typing import Any, Callable, TypeVar

from .config import AzureConfig, ConfigError, get_config

__all__ = ["AzureContentSafetyClient", "AzureClientError"]

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry configuration (matches OllamaClient)
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 1.0  # seconds, doubles each retry


class AzureClientError(Exception):
    """Raised when an Azure Content Safety API call fails."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


def _get_credential(azure_config: AzureConfig) -> Any:
    """Create the appropriate credential based on auth mode."""
    if azure_config.auth_mode == "identity":
        from azure.identity import DefaultAzureCredential

        return DefaultAzureCredential()
    else:
        from azure.core.credentials import AzureKeyCredential

        return AzureKeyCredential(azure_config.content_safety_key)


class AzureContentSafetyClient:
    """Client for Azure AI Content Safety operations.

    Wraps the azure-ai-contentsafety SDK with simplified methods for
    each safety feature. Can be used as a context manager.
    """

    def __init__(
        self,
        azure_config: AzureConfig | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    ) -> None:
        self._azure_config = azure_config or get_config().azure
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._total_retries = 0
        self._total_calls = 0
        if not self._azure_config.content_safety_available:
            raise AzureClientError(
                "Azure Content Safety is not configured. "
                "Set AZURE_CONTENT_SAFETY_ENDPOINT and AZURE_CONTENT_SAFETY_KEY."
            )

        from azure.ai.contentsafety import ContentSafetyClient

        credential = _get_credential(self._azure_config)
        self._client = ContentSafetyClient(
            endpoint=self._azure_config.content_safety_endpoint,
            credential=credential,
        )

    def __enter__(self) -> "AzureContentSafetyClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    @property
    def retry_stats(self) -> dict[str, int]:
        """Return retry statistics: total calls and total retries."""
        return {"total_calls": self._total_calls, "total_retries": self._total_retries}

    def _retry(self, fn: Callable[[], T], operation: str) -> T:
        """Execute fn with retry logic for transient connection failures.

        Retries on ConnectionError and OSError with exponential backoff.
        """
        self._total_calls += 1
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return fn()
            except (ConnectionError, OSError) as e:
                last_error = e
                self._total_retries += 1
                if attempt < self.max_retries - 1:
                    delay = self.retry_backoff * (2 ** attempt)
                    logger.warning(
                        "%s failed (attempt %d/%d), retrying in %.1fs: %s",
                        operation, attempt + 1, self.max_retries, delay, e,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "%s failed after %d attempts: %s",
                        operation, self.max_retries, e,
                    )
        raise AzureClientError(
            f"{operation} failed after {self.max_retries} attempts",
            cause=last_error,
        )

    def health_check(self) -> dict[str, Any]:
        """Check connectivity to the Azure Content Safety endpoint.

        Returns:
            Dict with 'healthy' (bool), 'endpoint' (str), and 'error' (str|None).
        """
        endpoint = self._azure_config.content_safety_endpoint
        try:
            # Use a minimal analyze_text call to verify connectivity
            self.analyze_text("health check", categories=["Hate"])
            return {"healthy": True, "endpoint": endpoint, "error": None}
        except AzureClientError as e:
            return {"healthy": False, "endpoint": endpoint, "error": str(e)}

    def analyze_text(
        self,
        text: str,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """Analyze text for harmful content across 4 categories.

        Args:
            text: The text to analyze (max 10K characters).
            categories: Optional list of categories to check. Defaults to all four:
                ["Hate", "Violence", "Sexual", "SelfHarm"].

        Returns:
            Dict with keys for each category containing severity (0-7)
            and a boolean 'flagged' if severity > 0.
        """
        from azure.ai.contentsafety.models import (
            AnalyzeTextOptions,
            TextCategory,
        )

        category_map = {
            "Hate": TextCategory.HATE,
            "Violence": TextCategory.VIOLENCE,
            "Sexual": TextCategory.SEXUAL,
            "SelfHarm": TextCategory.SELF_HARM,
        }

        request_categories = None
        if categories:
            request_categories = [
                category_map[c] for c in categories if c in category_map
            ]

        try:
            options = AnalyzeTextOptions(text=text, categories=request_categories)
            response = self._retry(
                lambda: self._client.analyze_text(options), "analyze_text"
            )
        except AzureClientError:
            raise
        except Exception as e:
            raise AzureClientError(f"analyze_text failed: {e}", cause=e) from e

        results: dict[str, Any] = {}
        if response.categories_analysis:
            for item in response.categories_analysis:
                cat_name = item.category.value if hasattr(item.category, "value") else str(item.category)
                results[cat_name] = {
                    "severity": item.severity,
                    "flagged": item.severity > 0,
                }
        return results

    def prompt_shield(
        self,
        user_prompt: str,
        documents: list[str] | None = None,
    ) -> dict[str, Any]:
        """Detect jailbreak attempts and indirect prompt injections.

        Args:
            user_prompt: The user's prompt to check (max 10K characters).
            documents: Optional list of documents to check for hidden
                injections (max 5 documents).

        Returns:
            Dict with 'userPromptAttack' and 'documentAttack' results,
            each containing 'detected' (bool) and 'attackType' (str).
        """
        from azure.ai.contentsafety.models import ShieldPromptOptions

        try:
            options = ShieldPromptOptions(
                user_prompt=user_prompt,
                documents=documents or [],
            )
            response = self._retry(
                lambda: self._client.shield_prompt(options), "prompt_shield"
            )
        except AzureClientError:
            raise
        except Exception as e:
            raise AzureClientError(f"prompt_shield failed: {e}", cause=e) from e

        result: dict[str, Any] = {
            "userPromptAttack": {
                "detected": False,
                "attackType": "none",
            },
            "documentAttack": {
                "detected": False,
                "attackType": "none",
            },
        }
        if response.user_prompt_analysis:
            result["userPromptAttack"] = {
                "detected": response.user_prompt_analysis.attack_detected,
                "attackType": str(
                    getattr(response.user_prompt_analysis, "attack_type", "unknown")
                ),
            }
        if response.documents_analysis:
            for doc_analysis in response.documents_analysis:
                if doc_analysis.attack_detected:
                    result["documentAttack"] = {
                        "detected": True,
                        "attackType": str(
                            getattr(doc_analysis, "attack_type", "unknown")
                        ),
                    }
                    break
        return result

    def detect_groundedness(
        self,
        text: str,
        grounding_sources: list[str],
        domain: str = "Generic",
        reasoning: bool = False,
    ) -> dict[str, Any]:
        """Detect whether text is grounded in the provided sources.

        Args:
            text: The LLM-generated text to check.
            grounding_sources: List of source texts to verify against.
            domain: "Generic" or "Medical".
            reasoning: If True, returns detailed reasoning about ungrounded segments.

        Returns:
            Dict with 'grounded' (bool), 'ungroundedPercentage' (float),
            and optionally 'reasoning' (list of ungrounded segments).
        """
        try:
            # Groundedness detection uses a REST-style call
            body: dict[str, Any] = {
                "domain": domain,
                "task": "QnA",
                "text": text,
                "groundingSources": grounding_sources,
                "reasoning": reasoning,
            }

            def _call_groundedness() -> Any:
                resp = self._client._client.send_request(
                    "POST",
                    "/text/groundedness:analyze",
                    json=body,
                    params={"api-version": "2024-09-15-preview"},
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                return resp.json()

            data = self._retry(_call_groundedness, "detect_groundedness")
        except AzureClientError:
            raise
        except Exception as e:
            raise AzureClientError(
                f"detect_groundedness failed: {e}", cause=e
            ) from e

        return {
            "grounded": data.get("ungroundedDetected", True) is False,
            "ungroundedPercentage": data.get("ungroundedPercentage", 0.0),
            "reasoning": data.get("ungroundedDetails", []) if reasoning else [],
        }

    def detect_protected_material(
        self,
        text: str,
    ) -> dict[str, Any]:
        """Detect copyrighted or protected material in text.

        Args:
            text: The text to check (min 110 characters for text detection).

        Returns:
            Dict with 'detected' (bool) and 'details' about matched material.
        """
        try:
            body = {"text": text}

            def _call_protected_material() -> Any:
                resp = self._client._client.send_request(
                    "POST",
                    "/text/protectedMaterial:analyze",
                    json=body,
                    params={"api-version": "2024-09-15-preview"},
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                return resp.json()

            data = self._retry(_call_protected_material, "detect_protected_material")
        except AzureClientError:
            raise
        except Exception as e:
            raise AzureClientError(
                f"detect_protected_material failed: {e}", cause=e
            ) from e

        analysis = data.get("protectedMaterialAnalysis", {})
        return {
            "detected": analysis.get("detected", False),
            "details": analysis,
        }

    def analyze_custom_category(
        self,
        text: str,
        category_name: str,
    ) -> dict[str, Any]:
        """Analyze text against a custom content category.

        Args:
            text: The text to analyze.
            category_name: The name of the custom category to check against.

        Returns:
            Dict with 'detected' (bool) and 'confidence' (float).
        """
        try:
            body = {
                "text": text,
                "categoryName": category_name,
            }

            def _call_custom_category() -> Any:
                resp = self._client._client.send_request(
                    "POST",
                    "/text/customCategories:analyze",
                    json=body,
                    params={"api-version": "2024-09-15-preview"},
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                return resp.json()

            data = self._retry(_call_custom_category, "analyze_custom_category")
        except AzureClientError:
            raise
        except Exception as e:
            raise AzureClientError(
                f"analyze_custom_category failed: {e}", cause=e
            ) from e

        analysis = data.get("customCategoryAnalysis", {})
        return {
            "detected": analysis.get("detected", False),
            "confidence": analysis.get("confidence", 0.0),
        }
