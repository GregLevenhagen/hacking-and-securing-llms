"""Live chatbot with Prompt Shields pre-screening every message.

Every user message is scanned by Azure Prompt Shields before reaching
the LLM. Blocked messages show a red shield indicator; safe messages
show green.
"""

import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient  # noqa: E402


SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer questions accurately. "
    "Be concise and informative."
)


class RealtimeShieldedChatbot:
    """Chatbot with Prompt Shields pre-screening on every message."""

    def __init__(
        self,
        client: Any = None,
        safety_client: Any = None,
    ) -> None:
        self.client = client or OllamaClient()
        self.safety_client = safety_client
        self.history: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def send(self, user_input: str) -> dict[str, Any]:
        """Pre-screen with Prompt Shields, then send to LLM if safe.

        Returns:
            Dict with: response, blocked, shield_result, status.
        """
        # Step 1: Pre-screen with Prompt Shields
        shield_result: dict[str, Any] = {
            "userPromptAttack": {"detected": False, "attackType": "none"},
            "documentAttack": {"detected": False, "attackType": "none"},
        }

        if self.safety_client:
            shield_result = self.safety_client.prompt_shield(user_input)

        user_attack = shield_result.get("userPromptAttack", {})
        if user_attack.get("detected", False):
            return {
                "response": (
                    f"🛡️ [BLOCKED] Jailbreak attempt detected "
                    f"(type: {user_attack.get('attackType', 'unknown')})"
                ),
                "blocked": True,
                "shield_result": shield_result,
                "status": "blocked",
            }

        # Step 2: Send to LLM
        self.history.append({"role": "user", "content": user_input})

        response = str(self.client.chat(self.history))
        self.history.append({"role": "assistant", "content": response})

        return {
            "response": response,
            "blocked": False,
            "shield_result": shield_result,
            "status": "safe",
        }

    def reset(self) -> None:
        """Reset conversation history."""
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
